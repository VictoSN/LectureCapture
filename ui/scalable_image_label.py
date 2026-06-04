from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

class ScalableImageLabel(QLabel):
    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self._pixmap = pixmap
        self.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setMinimumHeight(50)

    def resizeEvent(self, event):
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        super().resizeEvent(event)