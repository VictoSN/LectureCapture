from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from models.lecture import OCRCapture
from ui.capture_feed_panel import CaptureFeedPanel
from ui.styles import create_button, NoLeakTextEdit
from ui.format_time import FormatClock
from ui.mathtext import render_math
from ui.scalable_image_label import ScalableImageLabel

from pathlib import Path

# Width of the thumbnail kept in memory per capture. The full-resolution image
# is loaded from disk only when previewed, so long sessions stay bounded in RAM.
THUMBNAIL_WIDTH = 640


class OCRPanel(CaptureFeedPanel):
    ocr_text_changed = pyqtSignal(int, str) # capture_id & new text
    capture_added = pyqtSignal()  # emitted after add_capture so parent can sync heights
    capture_deleted = pyqtSignal(int)  # capture_id

    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__(base_dir, icons_dir, 'scan.svg', 'Screen OCR',
                         "Toggle OCR text editing", (10, 8, 8, 8))
        self.ocr_button = self.lock_button  # established name (TranscriptPanel, tests)
        self._panel_count = 0  # incremented for each capture widget added

    def _emit_text_changed(self, capture_id: int, text: str) -> None:
        self.ocr_text_changed.emit(capture_id, text)

    def _load_thumbnail(self, image_path: str) -> QPixmap | None:
        """Decode the screenshot directly at thumbnail width via QImageReader, so the
        full-resolution bitmap is never materialized. Loading a long session previously
        decoded every 1080p/4K PNG in full on the UI thread just to shrink it to 640px;
        QImageReader reads the header for the size, then decodes scaled in one pass.
        Returns None when the file is missing/unreadable."""
        reader = QImageReader(image_path)
        reader.setAutoTransform(True)
        size = reader.size()  # from the header — no full decode
        if size.isValid() and size.width() > THUMBNAIL_WIDTH:
            height = max(1, round(size.height() * THUMBNAIL_WIDTH / size.width()))
            reader.setScaledSize(QSize(THUMBNAIL_WIDTH, height))
        image = reader.read()
        if image.isNull():
            return None
        return QPixmap.fromImage(image)

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        self._panel_count += 1
        panel_number = self._panel_count

        capture_widget = QWidget()
        capture_layout = QVBoxLayout(capture_widget)
        capture_layout.setContentsMargins(0, 0, 0, 0)
        capture_layout.setSpacing(0)
        # No fixed height — height is controlled externally by sync_row_heights

        # Header row: [🗑] [📷] Panel N: H:MM:SS
        timestamp_row = QHBoxLayout()
        timestamp_row.setContentsMargins(4, 6, 4, 4)
        timestamp_row.setSpacing(6)
        delete_button = create_button(self.icons_dir / 'delete.svg', lambda: self._confirm_delete(capture.id, capture_widget))
        delete_button.setToolTip("Delete this capture")
        delete_button.setProperty("role", "delete")  # tagged so set_busy() can disable it
        delete_button.setDisabled(self._busy)
        timestamp_row.addWidget(delete_button)

        # Toggle image visibility — starts visible, click to collapse/expand
        toggle_img_btn = create_button(self.icons_dir / 'minimize.svg', None)
        toggle_img_btn.setToolTip("Hide image")
        timestamp_row.addWidget(toggle_img_btn)

        capture_timestamp = QLabel(f"Panel {panel_number}: {FormatClock(capture.timestamp)}")
        timestamp_row.addWidget(capture_timestamp)
        timestamp_row.addStretch()

        capture_layout.addLayout(timestamp_row)

        # Image — keep only a downscaled thumbnail in memory, decoded straight to
        # thumbnail size (see _load_thumbnail). The full-resolution screenshot is loaded
        # from disk on demand for preview only.
        image_path = str(Path(self.base_dir) / 'sessions' / str(capture.session_id) / 'captures' / capture.image_path)
        thumb = self._load_thumbnail(image_path)

        if thumb is None:
            capture_image = QLabel("[No image]")
            capture_image.setAlignment(Qt.AlignmentFlag.AlignTop)
        else:
            capture_image = ScalableImageLabel(thumb)
            capture_image.setCursor(Qt.CursorShape.PointingHandCursor)
            capture_image.mousePressEvent = lambda _e, p=image_path: self._show_full_image(p)

        # Text — render any LaTeX math spans to Unicode so symbols (∈, ℕ, ⊕ …)
        # show instead of raw "\in \mathbb{N}". Prose outside $...$ is untouched.
        ocr_text = NoLeakTextEdit()
        ocr_text.blockSignals(True)
        ocr_text.setPlainText(render_math(capture.extracted_text or ""))
        ocr_text.blockSignals(False)
        ocr_text.setReadOnly(self.is_locked or self._busy)
        ocr_text.lookup_requested.connect(self.lookup_requested)

        # Wire the toggle button now that capture_image exists.
        def _toggle_image():
            visible = not capture_image.isVisible()
            capture_image.setVisible(visible)
            toggle_img_btn.setToolTip("Hide image" if visible else "Show image")

        toggle_img_btn.clicked.connect(_toggle_image)

        # Stack image above text with a small breathing gap. ScalableImageLabel
        # caps its own height to the aspect-ratio height for the current width,
        # so the text below takes whatever vertical space is left over.
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        content_layout.addWidget(capture_image)
        content_layout.addWidget(ocr_text, stretch=1)
        capture_layout.addLayout(content_layout, stretch=1)

        self._wire_save_timer(ocr_text, capture.id)

        capture_widget.setProperty("capture_id", capture.id)
        return capture_widget

    def _confirm_delete(self, capture_id: int, widget: QWidget) -> None:
        reply = QMessageBox.question(
            self,
            "Delete capture",
            "Delete this capture? This cannot be undone.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._delete_capture(capture_id, widget)

    def _delete_capture(self, capture_id: int, widget: QWidget) -> None:
        self.feed_layout.removeWidget(widget)
        widget.deleteLater()
        self.capture_deleted.emit(capture_id)
        self.lock_button.setDisabled(not self.has_content())

    def _show_full_image(self, image_path: str) -> None:
        # Full-resolution preview with zoom + pan in a freely resizable window
        # (decoded full-size here, on demand — the feed only keeps a thumbnail).
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        from ui.image_preview import ImagePreviewDialog
        dialog = ImagePreviewDialog(pixmap, self)
        dialog.exec()

    def clear_captures(self) -> None:
        self._panel_count = 0
        super().clear_captures()

    def add_capture(self, capture: OCRCapture) -> None:
        super().add_capture(capture)
        self.capture_added.emit()
