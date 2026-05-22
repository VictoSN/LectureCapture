from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QTextEdit
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from models.lecture import OCRCapture
from pathlib import Path

class OCRPanel(QWidget):
    def __init__(self, base_dir):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir

        # Header Layout
        ocr_label = QLabel("Screen OCR")
        header.addWidget(ocr_label)
        self.ocr_button = QPushButton("Editable")
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

    def load_captures(self, captures: list[OCRCapture]):
        # Clear out the layout first
        while self.feed_layout.count():
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for capture in captures:
            capture_widget = QWidget()
            capture_layout = QVBoxLayout()
            
            # OCR Image
            capture_image = QLabel()
            capture_layout.addWidget(capture_image)
            
            pixmap = QPixmap(str(Path(self.base_dir) / 'sessions' / str(capture.session_id) / 'captures' / capture.image_path))
            capture_image.setPixmap(pixmap)
            capture_image.setAlignment(Qt.AlignmentFlag.AlignTop)

            # Timestamp & Extracted ocr text
            capture_timestamp = QLabel(f"{capture.timestamp:.2f}s")
            capture_layout.addWidget(capture_timestamp)
            
            capture_text = QTextEdit(capture.extracted_text)
            capture_layout.addWidget(capture_text)
            
            capture_widget.setLayout(capture_layout)
            self.feed_layout.addWidget(capture_widget)