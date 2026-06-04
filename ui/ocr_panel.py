from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QTextEdit
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from models.lecture import OCRCapture
from pathlib import Path

class OCRPanel(QWidget):
    ocr_text_changed = pyqtSignal(int, str) # capture_id & new text
    immediate_change = pyqtSignal()
    
    def __init__(self, base_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir
        self.is_locked = True

        # Header Layout
        ocr_label = QLabel("Screen OCR")
        header.addWidget(ocr_label)
        self.ocr_button = QPushButton("Locked")
        self.ocr_button.clicked.connect(self.set_locked)
        header.addWidget(self.ocr_button)

        # Scrollable
        self.feed_widget = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_widget)

        scroll = QScrollArea()
        scroll.setWidget(self.feed_widget)
        scroll.setWidgetResizable(True)

        main_layout.addLayout(header)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        capture_widget = QWidget()
        capture_layout = QVBoxLayout()
        
        # OCR Image
        capture_image = QLabel()
        capture_layout.addWidget(capture_image)
        
        pixmap = QPixmap(str(Path(self.base_dir) / 'sessions' / str(capture.session_id) / 'captures' / capture.image_path))
        
        # Check if image Exist
        if pixmap.isNull():
            capture_image.setText("[No image]")
        else:
            capture_image.setPixmap(pixmap)
        capture_image.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Timestamp & Extracted ocr text
        capture_timestamp = QLabel(f"{capture.timestamp:.2f}s")
        capture_layout.addWidget(capture_timestamp)
        
        ocr_text = QTextEdit()
        ocr_text.blockSignals(True)
        ocr_text.setPlainText(capture.extracted_text or "")
        ocr_text.blockSignals(False)
        ocr_text.setReadOnly(self.is_locked)
        
        # Update after 500ms
        timer = QTimer(ocr_text)
        timer.setSingleShot(True)
        ocr_text._save_timer = timer
        
        ocr_text.textChanged.connect(self.immediate_change)
        ocr_text.textChanged.connect(lambda: ocr_text._save_timer.start(500))

        ocr_text._save_timer.timeout.connect(
            lambda cap_id=capture.id, w=ocr_text:
                self.ocr_text_changed.emit(cap_id, w.toPlainText())
        )
        
        capture_layout.addWidget(ocr_text)
        
        capture_widget.setProperty("capture_id", capture.id)
        capture_widget.setLayout(capture_layout)
        return capture_widget # Return to load and add methods

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