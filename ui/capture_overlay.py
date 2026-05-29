from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap
import mss, mss.tools

class CaptureOverlay(QWidget):
    def __init__(self, callback, cancel_callback):
        super().__init__()
        self.callback = callback
        self.cancel_callback = cancel_callback
        self.start = None
        self.end = None
        
        self.sct = mss.mss()
        self.background = self._grab_screen()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint 
        )
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.show()
        self.activateWindow()

    def _grab_screen(self):
        monitor = self.sct.monitors[2]
        img = self.sct.grab(monitor)

        pixmap = QPixmap()
        pixmap.loadFromData(mss.tools.to_png(img.rgb, img.size))

        screen = QApplication.primaryScreen()
        return pixmap.scaled(
            screen.geometry().width(),
            screen.geometry().height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
    
    def paintEvent(self, event):
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

    def mousePressEvent(self, event):
        self.start = event.position()

    def mouseMoveEvent(self, event):
        self.end = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        self.end = event.position()
        x1, y1 = int(self.start.x()), int(self.start.y())
        x2, y2 = int(self.end.x()), int(self.end.y())
        self.callback(min(x1, x2), min(y1, y2), abs(x1 - x2), abs(y1 - y2))
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancel_callback()