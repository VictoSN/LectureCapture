"""Full-screen-resizable image viewer with zoom + pan, used for previewing a captured
slide at full resolution (OCRPanel._show_full_image).

Built on QGraphicsView/QGraphicsScene so pan and cursor-anchored zoom come essentially
for free:
  * mouse wheel  — zoom in/out about the cursor
  * drag         — pan (ScrollHandDrag)
  * double-click / F / 0 — fit the whole image to the window
  * 1            — 100% (actual pixels)
  * +/-          — zoom in/out
  * Esc          — close
The dialog opens large and is freely resizable; while "fitted" it keeps the image fit
to the window as it's resized.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
)
from PyQt6.QtGui import QPixmap, QPainter, QGuiApplication
from PyQt6.QtCore import Qt, QEvent


class ImagePreviewDialog(QDialog):
    MIN_SCALE = 0.05
    MAX_SCALE = 20.0
    _ZOOM_STEP = 1.25

    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Image Preview")
        self._pixmap = pixmap
        self._fitted = True   # while True, track the window size (fit-to-window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem(pixmap)
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._item)

        self._view = QGraphicsView(self._scene, self)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._view.setRenderHints(
            QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
        self._view.viewport().installEventFilter(self)  # wheel + double-click
        layout.addWidget(self._view)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.85), int(screen.height() * 0.85))

    # ---- fit / zoom ------------------------------------------------------

    def _fit(self) -> None:
        self._view.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def fit_to_window(self) -> None:
        self._fitted = True
        self._fit()

    def actual_size(self) -> None:
        self._fitted = False
        self._view.resetTransform()

    def current_scale(self) -> float:
        return self._view.transform().m11()

    @classmethod
    def _allowed_zoom(cls, current_scale: float, factor: float) -> bool:
        """Whether applying `factor` keeps the scale within [MIN_SCALE, MAX_SCALE]."""
        new_scale = current_scale * factor
        return cls.MIN_SCALE <= new_scale <= cls.MAX_SCALE

    def zoom(self, factor: float) -> None:
        if not self._allowed_zoom(self.current_scale(), factor):
            return  # clamp — ignore a step that would exceed the limits
        self._fitted = False
        self._view.scale(factor, factor)

    # ---- events ----------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._fitted:
            self._fit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:   # only auto-refit until the user manually zooms
            self._fit()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._view.viewport():
            if event.type() == QEvent.Type.Wheel:
                self.zoom(self._ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self._ZOOM_STEP)
                return True
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.fit_to_window()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom(self._ZOOM_STEP)
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoom(1 / self._ZOOM_STEP)
        elif key in (Qt.Key.Key_F, Qt.Key.Key_0):
            self.fit_to_window()
        elif key == Qt.Key.Key_1:
            self.actual_size()
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
