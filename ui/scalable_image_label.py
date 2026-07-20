from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QSize


class ScalableImageLabel(QLabel):
    """QLabel that scales its pixmap to available width while preserving aspect ratio."""

    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self._pixmap = pixmap
        self._last_w = -1
        self.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setMinimumHeight(40)
        # Layout dictates width; height is derived from aspect ratio.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)

    def _aspect_h(self, width: int) -> int:
        if self._pixmap.isNull() or self._pixmap.width() <= 0:
            return self.minimumHeight()
        ratio = self._pixmap.height() / self._pixmap.width()
        return max(self.minimumHeight(), int(round(width * ratio)))

    def minimumSizeHint(self) -> QSize:
        return QSize(1, self.minimumHeight())

    def sizeHint(self) -> QSize:
        w = self.width() if self.width() > 0 else min(self._pixmap.width(), 320)
        return QSize(w, self._aspect_h(w))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap.isNull():
            return
        w = self.width()
        if w <= 0 or w == self._last_w:
            return
        self._last_w = w
        h = self._aspect_h(w)
        self.setMaximumHeight(h)
        # Scale in device pixels so the image stays sharp on high-DPI displays.
        dpr = self.devicePixelRatioF()
        scaled = self._pixmap.scaled(
            round(w * dpr), round(h * dpr),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self.setPixmap(scaled)
