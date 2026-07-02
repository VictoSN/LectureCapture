from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QSize


class ScalableImageLabel(QLabel):
    """A QLabel that scales its pixmap to the available width while preserving
    the original aspect ratio.

    Two details make this behave correctly inside a QScrollArea, where a plain
    pixmap QLabel does not:

    * ``minimumSizeHint`` is forced tiny.  A normal pixmap QLabel reports the
      *full pixmap size* as its minimum, so the surrounding layout / scroll-area
      refuses to make it (and therefore its row) any narrower -- that is exactly
      why such an image can grow but never shrink.  By reporting a 1px-wide
      minimum we let the layout drive the width freely in both directions.

    * Width is owned by the layout (``Ignored`` horizontal policy); height is
      derived from that width via ``maximumHeight``/``sizeHint`` (``Maximum``
      vertical policy).  We only recompute on a genuine width change so the
      image height never feeds back into the scroll-area content height and
      oscillates (that oscillation is what froze and crashed the app on session
      switches).
    """

    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self._pixmap = pixmap
        self._last_w = -1
        self.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setMinimumHeight(40)
        # Layout dictates width (Ignored); height never exceeds the aspect-ratio
        # height we advertise via sizeHint()/maximumHeight() (Maximum).
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)

    def _aspect_h(self, width: int) -> int:
        if self._pixmap.isNull() or self._pixmap.width() <= 0:
            return self.minimumHeight()
        ratio = self._pixmap.height() / self._pixmap.width()
        return max(self.minimumHeight(), int(round(width * ratio)))

    def minimumSizeHint(self) -> QSize:
        # Never let the pixmap impose a large minimum width -> always shrinkable.
        return QSize(1, self.minimumHeight())

    def sizeHint(self) -> QSize:
        # Preferred (and, with the Maximum policy, the cap) height at the current
        # width.  Fall back to a modest reference width before the first layout
        # so freshly created rows don't briefly demand the full thumbnail height.
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
        # Scale in device pixels, not logical ones: on a scaled display (e.g. 125%)
        # a pixmap scaled to the logical width gets stretched back up by the DPR
        # and turns blurry. Tagging the result with the DPR keeps its on-screen
        # (logical) size the same while giving the screen every physical pixel.
        dpr = self.devicePixelRatioF()
        scaled = self._pixmap.scaled(
            round(w * dpr), round(h * dpr),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self.setPixmap(scaled)
