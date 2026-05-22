from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel
)

class OCRPanel(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()

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