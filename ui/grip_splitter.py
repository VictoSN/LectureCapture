from PyQt6.QtWidgets import QSplitter, QSplitterHandle
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPainterPath


_BAR_THICKNESS = 3   # px, width of the hover indicator bar
_BAR_LENGTH = 48     # px, how long the bar spans (perpendicular axis)
_BAR_RADIUS = 2      # px, rounded cap radius


class GripHandle(QSplitterHandle):
    """Splitter handle that shows a centred rounded bar on hover."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hovered = False
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self._hovered = True
        self.raise_()   # float above panel edges
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._hovered:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        base = self.palette().window().color()
        bar_color = QColor("#6b6460") if base.lightness() < 128 else QColor("#b8b0a0")
        painter.setBrush(bar_color)
        painter.setPen(Qt.PenStyle.NoPen)

        w, h = self.width(), self.height()

        if self.orientation() == Qt.Orientation.Horizontal:
            # Vertical bar centred horizontally, spanning _BAR_LENGTH px
            bx = (w - _BAR_THICKNESS) // 2
            by = (h - _BAR_LENGTH) // 2
            rect = QRect(bx, by, _BAR_THICKNESS, _BAR_LENGTH)
        else:
            # Horizontal bar centred vertically
            bx = (w - _BAR_LENGTH) // 2
            by = (h - _BAR_THICKNESS) // 2
            rect = QRect(bx, by, _BAR_LENGTH, _BAR_THICKNESS)

        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(),
                            _BAR_RADIUS, _BAR_RADIUS)
        painter.drawPath(path)
        painter.end()


class GripSplitter(QSplitter):
    """QSplitter that uses GripHandle and a slightly wider hit area."""

    _HANDLE_WIDTH = 8  # wide enough to paint into; looks thin via bg match

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setHandleWidth(self._HANDLE_WIDTH)

    def createHandle(self):
        return GripHandle(self.orientation(), self)
