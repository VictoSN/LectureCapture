from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QSplitter, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt

from ui.ocr_panel import OCRPanel
from ui.speech_panel import SpeechPanel
from ui.summary_panel import SummaryPanel

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
        self.speech_visibility_button = QPushButton("S2T")
        header.addWidget(self.speech_visibility_button)
        self.summary_visibility_button = QPushButton("AI")
        header.addWidget(self.summary_visibility_button)
        
        self.record_button = QPushButton("Record")
        header.addWidget(self.record_button)

        # Splitter Layout for content
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        ocr_panel = OCRPanel()
        speech_panel = SpeechPanel()
        summary_panel = SummaryPanel()
        
        self.splitter.addWidget(ocr_panel)
        self.splitter.addWidget(speech_panel)
        self.splitter.addWidget(summary_panel)
        self.splitter.setSizes([100, 100, 100]) # 1 : 4 ratio
        
        main_layout.addLayout(header)
        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)
        