import math
import mss, mss.tools

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap

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
            cx, cy = (left + right) // 2, (top + bottom) // 2
            ratio = 1.0

            for s in QApplication.screens():
                sg = s.geometry()
                phys_x = int(sg.x() * s.devicePixelRatio())
                phys_y = int(sg.y() * s.devicePixelRatio())
                phys_w = int(sg.width() * s.devicePixelRatio())
                phys_h = int(sg.height() * s.devicePixelRatio())
                
                if (
                    phys_x <= cx < phys_x + phys_w
                    and phys_y <= cy < phys_y + phys_h
                ):
                    ratio = s.devicePixelRatio()
                    break

            self.setGeometry(
                int(left / ratio),
                int(top / ratio),
                math.ceil((right - left) / ratio),
                math.ceil((bottom - top) / ratio)
            )
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.show()
        self.activateWindow()
        
        # Focus to enable ESC to work
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.grabKeyboard()

    def _grab_screen(self) -> tuple[QPixmap, QRect]:
        if self.hwnd:
            import win32gui
            from core.ocr import OCRWorker
            from PyQt6.QtGui import QImage

            pil_img = OCRWorker.get_window_screenshot_static(self.hwnd)
            pil_img = pil_img.convert("RGBA")
            width, height = pil_img.size
            data = pil_img.tobytes("raw", "RGBA")
            qimage = QImage(
                data,
                width,
                height,
                width * 4,
                QImage.Format.Format_RGBA8888
            ).copy()
            pixmap = QPixmap.fromImage(qimage)
            
            left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
            cx, cy = (left + right) // 2, (top + bottom) // 2
            ratio = 1.0

            for s in QApplication.screens():
                sg = s.geometry()
                phys_x = int(sg.x() * s.devicePixelRatio())
                phys_y = int(sg.y() * s.devicePixelRatio())
                phys_w = int(sg.width() * s.devicePixelRatio())
                phys_h = int(sg.height() * s.devicePixelRatio())

                if (
                    phys_x <= cx < phys_x + phys_w
                    and phys_y <= cy < phys_y + phys_h
                ):
                    ratio = s.devicePixelRatio()
                    break

            logical_w = math.ceil((right - left) / ratio)
            logical_h = math.ceil((bottom - top) / ratio)

            pixmap = pixmap.scaled(
                logical_w,
                logical_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            window_rect = pixmap.rect()

        else:
            m = self.sct.monitors[self.monitor_index]
            img = self.sct.grab(m)

            pixmap = QPixmap()
            pixmap.loadFromData(
                mss.tools.to_png(img.rgb, img.size)
            )
            screens = QApplication.screens()
            screen = screens[0]

            for s in screens:
                ratio = s.devicePixelRatio()
                phys_x = int(s.geometry().x() * ratio)
                phys_y = int(s.geometry().y() * ratio)

                if phys_x == m["left"] and phys_y == m["top"]:
                    screen = s
                    break

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
        painter.drawPixmap(self.rect(), self.background) # Set screenshot as background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120)) # Make the entire screen dark

        if self.start and self.end:
            rect = QRect(self.start.toPoint(), self.end.toPoint()).normalized()
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
            ratio = self.devicePixelRatioF()

            self.callback(
                int(min(x1, x2) * ratio),
                int(min(y1, y2) * ratio),
                int(abs(x1 - x2) * ratio),
                int(abs(y1 - y2) * ratio)
            )
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