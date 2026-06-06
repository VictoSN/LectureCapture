from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QTextEdit, QSplitter, QDialog
)
from PyQt6.QtGui import QPixmap, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from models.lecture import OCRCapture
from ui.styles import create_label, create_button
from ui.scalable_image_label import ScalableImageLabel

from pathlib import Path

# Width of the thumbnail kept in memory per capture. The full-resolution image
# is loaded from disk only when previewed, so long sessions stay bounded in RAM.
THUMBNAIL_WIDTH = 640


class OCRPanel(QWidget):
    ocr_text_changed = pyqtSignal(int, str) # capture_id & new text
    immediate_change = pyqtSignal()
    capture_added = pyqtSignal()  # emitted after add_capture so parent can sync heights
    capture_deleted = pyqtSignal(int)  # capture_id
    
    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir
        self.icons_dir = icons_dir
        self.is_locked = True

        # Header Layout
        ocr_w, self.ocr_engine_label = create_label(icons_dir / 'scan.svg', 'Screen OCR')
        header.addWidget(ocr_w)
        
        self.ocr_button = QPushButton("Locked")
        self.ocr_button.clicked.connect(self.set_locked)
        header.addWidget(self.ocr_button)

        # Scrollable
        self.feed_widget = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_widget)
        self.feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # fixes centering bug

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.feed_widget)
        self.scroll.setWidgetResizable(True)

        main_layout.addLayout(header)
        main_layout.addWidget(self.scroll)
        self.setLayout(main_layout)

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        capture_widget = QWidget()
        capture_layout = QVBoxLayout(capture_widget)
        capture_layout.setContentsMargins(0, 0, 0, 0)
        # No fixed height — height is controlled externally by sync_row_heights

        # Timestamp row with delete button
        timestamp_row = QHBoxLayout()
        capture_timestamp = QLabel(f"{capture.timestamp:.2f}s")
        timestamp_row.addWidget(capture_timestamp)
        timestamp_row.addStretch()

        delete_button = create_button(self.icons_dir / 'delete.svg', lambda: self._delete_capture(capture.id, capture_widget))
        timestamp_row.addWidget(delete_button)

        capture_layout.addLayout(timestamp_row)

        # Vertical splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Image — keep only a downscaled thumbnail in memory. The full-resolution
        # screenshot is loaded from disk on demand for preview; otherwise a long
        # session would pin hundreds of full-size pixmaps in RAM and run out.
        image_path = str(Path(self.base_dir) / 'sessions' / str(capture.session_id) / 'captures' / capture.image_path)
        source = QPixmap(image_path)

        if source.isNull():
            capture_image = QLabel("[No image]")
            capture_image.setAlignment(Qt.AlignmentFlag.AlignTop)
        else:
            thumb = source.scaledToWidth(THUMBNAIL_WIDTH, Qt.TransformationMode.SmoothTransformation) if source.width() > THUMBNAIL_WIDTH else source
            capture_image = ScalableImageLabel(thumb)
            capture_image.setCursor(Qt.CursorShape.PointingHandCursor)
            capture_image.mousePressEvent = lambda _e, p=image_path: self._show_full_image(p)
        # `source` is released when this scope ends, freeing the full-res pixmap.

        splitter.addWidget(capture_image)

        # Text
        ocr_text = QTextEdit()
        ocr_text.blockSignals(True)
        ocr_text.setPlainText(capture.extracted_text or "")
        ocr_text.blockSignals(False)
        ocr_text.setReadOnly(self.is_locked)
        splitter.addWidget(ocr_text)

        splitter.setSizes([200, 300])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        capture_layout.addWidget(splitter, stretch=1)

        # Timer
        timer = QTimer(ocr_text)
        timer.setSingleShot(True)
        ocr_text._save_timer = timer
        ocr_text.textChanged.connect(self.immediate_change)
        ocr_text.textChanged.connect(lambda: ocr_text._save_timer.start(500))
        ocr_text._save_timer.timeout.connect(
            lambda cap_id=capture.id, w=ocr_text:
                self.ocr_text_changed.emit(cap_id, w.toPlainText())
        )

        capture_widget.setProperty("capture_id", capture.id)
        return capture_widget

    def _delete_capture(self, capture_id: int, widget: QWidget) -> None:
        self.feed_layout.removeWidget(widget)
        widget.deleteLater()
        self.capture_deleted.emit(capture_id)
        self.ocr_button.setDisabled(not self.has_content())

    def _show_full_image(self, image_path: str) -> None:
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Image Preview")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        label.setPixmap(pixmap.scaled(
            int(screen.width() * 0.8), int(screen.height() * 0.8),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        layout.addWidget(label)
        dialog.exec()
    
    def clear_captures(self) -> None:
        while self.feed_layout.count():
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_captures(self, captures: list[OCRCapture]) -> None:
        self.clear_captures()
        for capture in captures:
            self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.ocr_button.setDisabled(not self.has_content())
            
    def add_capture(self, capture: OCRCapture) -> None:
        self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.ocr_button.setDisabled(False)
        self.capture_added.emit()
        
    def set_locked(self) -> None:
        self.is_locked = not self.is_locked
        self.ocr_button.setText("Locked" if self.is_locked else "Editable")
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(self.is_locked)

    def has_content(self) -> bool:
        return self.feed_layout.count() > 0