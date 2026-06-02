import math
import mss, mss.tools
import ctypes
import ctypes.wintypes

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap, QImage

# DWM attribute for real window bounds (no shadow)
DWMWA_EXTENDED_FRAME_BOUNDS = 9

def _get_dwm_frame_rect(hwnd) -> ctypes.wintypes.RECT:
    # Get real visible window rect (DWM, no shadow padding).
    rect = ctypes.wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect), ctypes.sizeof(rect)
    )
    return rect

def _find_screen_ratio(cx: int, cy: int) -> float:
    # Find screen DPI scale for a pixel position. Used to match logical vs physical coordinates.
    for s in QApplication.screens():
        sg = s.geometry()
        ratio = s.devicePixelRatio()
        phys_x = int(sg.x() * ratio)
        phys_y = int(sg.y() * ratio)
        phys_w = int(sg.width()  * ratio)
        phys_h = int(sg.height() * ratio)
        if phys_x <= cx < phys_x + phys_w and phys_y <= cy < phys_y + phys_h:
            return ratio
    return 1.0

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
        
        # Take screenshot for overlay background
        self.background, self.window_rect = self._grab_screen()

        if hwnd:
            self._init_hwnd_overlay()
        else:
            self._init_monitor_overlay()

        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.show()
        self.activateWindow()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.grabKeyboard()

    def _init_hwnd_overlay(self) -> None:
        # Place overlay exactly over a window using DWM bounds.
        frame = _get_dwm_frame_rect(self.hwnd)
        cx, cy = (frame.left + frame.right) // 2, (frame.top + frame.bottom) // 2
        ratio = _find_screen_ratio(cx, cy)

        self.setGeometry(
            int(frame.left   / ratio),
            int(frame.top    / ratio),
            math.ceil((frame.right  - frame.left) / ratio),
            math.ceil((frame.bottom - frame.top)  / ratio),
        )
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

    def _init_monitor_overlay(self) -> None:
        # Cover full monitor as overlay.
        m = self.sct.monitors[self.monitor_index]
        target_screen = QApplication.screens()[0]

        for s in QApplication.screens():
            ratio = s.devicePixelRatio()
            if int(s.geometry().x() * ratio) == m["left"] and int(s.geometry().y() * ratio) == m["top"]:
                target_screen = s
                break
        self.setGeometry(target_screen.geometry())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowState(Qt.WindowState.WindowFullScreen)

    def _grab_screen(self) -> tuple[QPixmap, QRect]:
        if self.hwnd:
            return self._grab_hwnd_screen()
        return self._grab_monitor_screen()

    def _grab_hwnd_screen(self) -> tuple[QPixmap, QRect]:
        # Screenshot a window using PrintWindow and crop shadow padding.
        from core.ocr import OCRWorker

        pil_img = OCRWorker.get_window_screenshot_static(self.hwnd).convert("RGBA")
        frame = _get_dwm_frame_rect(self.hwnd)
        true_w = frame.right  - frame.left
        true_h = frame.bottom - frame.top
        pil_img = pil_img.crop((0, 0, true_w, true_h))

        w, h = pil_img.size
        qimage = QImage(pil_img.tobytes("raw", "RGBA"), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(qimage)

        cx, cy = (frame.left + frame.right) // 2, (frame.top + frame.bottom) // 2
        pixmap.setDevicePixelRatio(_find_screen_ratio(cx, cy))
        return pixmap, pixmap.rect()

    def _grab_monitor_screen(self) -> tuple[QPixmap, QRect]:
        # Screenshot monitor using mss at physical resolution.
        m = self.sct.monitors[self.monitor_index]
        img = self.sct.grab(m)

        screen = QApplication.screens()[0]
        for s in QApplication.screens():
            ratio = s.devicePixelRatio()
            if int(s.geometry().x() * ratio) == m["left"] and int(s.geometry().y() * ratio) == m["top"]:
                screen = s
                break
        pixmap = QPixmap()
        pixmap.loadFromData(mss.tools.to_png(img.rgb, img.size))
        pixmap.setDevicePixelRatio(screen.devicePixelRatio())
        return pixmap, screen.geometry()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)

        # Draw screenshot background
        painter.drawPixmap(0, 0, self.background)

        # Dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.start and self.end:
            rect = QRect(self.start.toPoint(), self.end.toPoint()).normalized()

            ratio = self.devicePixelRatioF()
            src_rect = QRect(
                int(rect.x()      * ratio),
                int(rect.y()      * ratio),
                int(rect.width()  * ratio),
                int(rect.height() * ratio),
            )

            # Clear selection area
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))

            # Redraw selection area
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(rect, self.background, src_rect)

            # Border
            painter.setPen(Qt.GlobalColor.red)
            painter.drawRect(rect.adjusted(-1, -1, 0, 0))

    def mousePressEvent(self, event) -> None:
        self.start = event.position()

    def mouseMoveEvent(self, event) -> None:
        self.end = event.position()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self.end = event.position()
        if self.start is None:
            self.close()
            return
        x1, y1 = int(self.start.x()), int(self.start.y())
        x2, y2 = int(self.end.x()),   int(self.end.y())

        if self.hwnd:
            ratio = self.devicePixelRatioF()
            self.callback(
                int(min(x1, x2) * ratio),
                int(min(y1, y2) * ratio),
                int(abs(x1 - x2) * ratio),
                int(abs(y1 - y2) * ratio),
            )
        else:
            ox, oy = self.geometry().topLeft().x(), self.geometry().topLeft().y()
            self.callback(min(x1, x2) + ox, min(y1, y2) + oy, abs(x1 - x2), abs(y1 - y2))
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancel_callback()