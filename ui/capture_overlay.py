from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap
import mss, mss.tools

class CaptureOverlay(QWidget):
    def __init__(self, callback, cancel_callback, monitor_index=None, hwnd=None) -> None:
        super().__init__()
        self.callback = callback
        self.cancel_callback = cancel_callback
        self.monitor_index = monitor_index
        self.hwnd = hwnd
        self.start = None
        self.end = None
        
        self.sct = mss.mss()
        self.background, self.window_rect = self._grab_screen()

        if hwnd:
            import win32gui
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            self.setGeometry(left, top, right - left, bottom - top)
            # For window overlays don't force fullscreen — it conflicts with the
            # positioned geometry and crashes on some setups.
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            # Match by physical pixel position: convert Qt logical coords to physical
            # before comparing against mss (which always uses physical pixels)
            m = self.sct.monitors[self.monitor_index]
            screens = QApplication.screens()
            target_screen = screens[0]  # fallback
            for s in screens:
                ratio = s.devicePixelRatio()
                phys_x = int(s.geometry().x() * ratio)
                phys_y = int(s.geometry().y() * ratio)
                if phys_x == m["left"] and phys_y == m["top"]:
                    target_screen = s
                    break
            self.setGeometry(target_screen.geometry())
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.setWindowState(Qt.WindowState.WindowFullScreen)

        self.setCursor(Qt.CursorShape.CrossCursor)
        self.show()
        self.activateWindow()
        
        # Focus to enable ESC to work
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.grabKeyboard()

    def _grab_screen(self) -> tuple[QPixmap, QRect]:
        if self.hwnd:
            from core.ocr import OCRWorker
            from PIL.ImageQt import ImageQt
            pil_img = OCRWorker.get_window_screenshot_static(self.hwnd)
            pixmap = QPixmap.fromImage(ImageQt(pil_img))
            window_rect = pixmap.rect()
        else:
            m = self.sct.monitors[self.monitor_index]
            img = self.sct.grab(m)

            pixmap = QPixmap()
            pixmap.loadFromData(mss.tools.to_png(img.rgb, img.size))

            # Match Qt screen using physical pixel coordinates
            screens = QApplication.screens()
            screen = screens[0]  # fallback
            for s in screens:
                ratio = s.devicePixelRatio()
                phys_x = int(s.geometry().x() * ratio)
                phys_y = int(s.geometry().y() * ratio)
                if phys_x == m["left"] and phys_y == m["top"]:
                    screen = s
                    break

            # Scale the raw physical-pixel screenshot down to Qt logical size
            pixmap = pixmap.scaled(
                screen.geometry().width(),
                screen.geometry().height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            window_rect = pixmap.rect()
        return pixmap, window_rect
    
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.background) # Set screenshot as background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120)) # Make the entire screen dark

        if self.start and self.end:
            rect = QRect(self.start.toPoint(), self.end.toPoint())
            # Cut out the selected area
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(rect, self.background, rect) # Redraw the screenshot in the selection area

            # Red border
            painter.setPen(Qt.GlobalColor.red)
            painter.drawRect(rect.adjusted(-1, -1, 0, 0)) # To avoid having rect being in the inside edge

    def mousePressEvent(self, event) -> None:
        self.start = event.position()

    def mouseMoveEvent(self, event) -> None:
        self.end = event.position()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self.end = event.position()
        x1, y1 = int(self.start.x()), int(self.start.y())
        x2, y2 = int(self.end.x()), int(self.end.y())

        if self.hwnd:
            # Coordinates are already relative to the window — pass them directly.
            # OCRWorker receives them as a crop region within the window screenshot.
            self.callback(min(x1, x2), min(y1, y2), abs(x1 - x2), abs(y1 - y2))
        else:
            # For monitor captures: coordinates are relative to the overlay widget
            # which sits at the monitor's logical origin.  Add the monitor's logical
            # origin so OCRWorker gets absolute screen coordinates, then OCRWorker
            # will subtract the monitor origin itself when building the mss region.
            origin = self.geometry().topLeft()
            ox, oy = origin.x(), origin.y()
            self.callback(min(x1, x2) + ox, min(y1, y2) + oy, abs(x1 - x2), abs(y1 - y2))

        self.close()
    
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancel_callback()