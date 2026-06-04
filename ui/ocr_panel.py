from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QTextEdit, QSplitter, QDialog
)
from PyQt6.QtGui import QPixmap, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from models.lecture import OCRCapture
from ui.widgets import create_label
from ui.scalable_image_label import ScalableImageLabel

from pathlib import Path

class OCRPanel(QWidget):
    ocr_text_changed = pyqtSignal(int, str) # capture_id & new text
    immediate_change = pyqtSignal()
    
    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir
        self.is_locked = True

        # Header Layout
        ocr_w, self.ocr_engine_label = create_label('scan.svg', 'Screen OCR', icons_dir)
        header.addWidget(ocr_w)
        
        self.ocr_button = QPushButton("Locked")
        self.ocr_button.clicked.connect(self.set_locked)
        header.addWidget(self.ocr_button)

        # Scrollable
        self.feed_widget = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_widget)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.feed_widget)
        self.scroll.setWidgetResizable(True)

        main_layout.addLayout(header)
        main_layout.addWidget(self.scroll)
        self.setLayout(main_layout)

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        capture_widget = QWidget()
        capture_layout = QVBoxLayout(capture_widget)
        capture_widget.setFixedHeight(300)
        capture_layout.setContentsMargins(0, 0, 0, 0)

        # Timestamp
        capture_timestamp = QLabel(f"{capture.timestamp:.2f}s")
        capture_layout.addWidget(capture_timestamp)

        # Vertical splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Image
        image_path = str(Path(self.base_dir) / 'sessions' / str(capture.session_id) / 'captures' / capture.image_path)
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            capture_image = QLabel("[No image]")
            capture_image.setAlignment(Qt.AlignmentFlag.AlignTop)
        else:
            capture_image = ScalableImageLabel(pixmap)
            capture_image.setCursor(Qt.CursorShape.PointingHandCursor)
            capture_image.mousePressEvent = lambda _: self._show_full_image(pixmap)

        splitter.addWidget(capture_image)

        # Text
        ocr_text = QTextEdit()
        ocr_text.blockSignals(True)
        ocr_text.setPlainText(capture.extracted_text or "")
        ocr_text.blockSignals(False)
        ocr_text.setReadOnly(self.is_locked)
        ocr_text.setMaximumHeight(300)
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

    def _show_full_image(self, pixmap: QPixmap) -> None:
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
        # Clear out the layout first
        while self.feed_layout.count():
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_captures(self, captures: list[OCRCapture]) -> None:
        self.clear_captures()
        
        for capture in captures:
            self.feed_layout.addWidget(self._create_capture_widget(capture))
            
        # Disable button if empty
        if self.has_content():
            self.ocr_button.setDisabled(False)
        else:
            self.ocr_button.setDisabled(True)
            
    def add_capture(self, capture: OCRCapture) -> None:
        self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.ocr_button.setDisabled(False)
        
    def set_locked(self) -> None:
        self.is_locked = not self.is_locked
        self.ocr_button.setText("Locked" if self.is_locked else "Editable")
        
        # Lock only the text edit
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(self.is_locked)

    def has_content(self) -> bool:
        return self.feed_layout.count() > 0