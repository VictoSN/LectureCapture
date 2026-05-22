from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QSplitter, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt


class TranscriptPanel(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        
        # Header Layout
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        header.addWidget(self.session_name)
        
        self.ocr_visibility_button = QPushButton("OCR")
        header.addWidget(self.ocr_visibility_button)
        self.s2t_visibility_button = QPushButton("S2T")
        header.addWidget(self.s2t_visibility_button)
        self.ai_visibility_button = QPushButton("AI")
        header.addWidget(self.ai_visibility_button)
        
        self.record_button = QPushButton("Record")
        header.addWidget(self.record_button)

        # Splitter Layout for content
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        ocr_panel = QWidget()
        s2t_panel = QWidget()
        ai_panel = QWidget()
        
        self.splitter.addWidget(ocr_panel)
        self.splitter.addWidget(s2t_panel)
        self.splitter.addWidget(ai_panel)
        
        main_layout.addLayout(header)
        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)