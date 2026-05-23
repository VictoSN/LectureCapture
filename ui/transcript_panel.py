from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QSplitter, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt, pyqtSignal

from models.lecture import Session, OCRCapture
from ui.ocr_panel import OCRPanel
from ui.speech_panel import SpeechPanel
from ui.summary_panel import SummaryPanel

class TranscriptPanel(QWidget):
    record_clicked = pyqtSignal()
    
    def __init__(self, base_dir):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir

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
        self.record_button.clicked.connect(self.record_clicked)
        header.addWidget(self.record_button)

        # Splitter Layout for content
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.ocr_panel = OCRPanel(base_dir)
        self.speech_panel = SpeechPanel(base_dir)
        self.summary_panel = SummaryPanel()

        # Button Visibility Function
        self.ocr_visibility_button.clicked.connect(
            lambda: self.ocr_panel.setVisible(not self.ocr_panel.isVisible())
        )
        self.speech_visibility_button.clicked.connect(
            lambda: self.speech_panel.setVisible(not self.speech_panel.isVisible())
        )
        self.summary_visibility_button.clicked.connect(
            lambda: self.summary_panel.setVisible(not self.summary_panel.isVisible())
        )

        self.splitter.addWidget(self.ocr_panel)
        self.splitter.addWidget(self.speech_panel)
        self.splitter.addWidget(self.summary_panel)
        self.splitter.setSizes([100, 100, 100]) # 1 : 4 ratio

        main_layout.addLayout(header)
        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)

    def load_session(self, session: Session, captures: OCRCapture):
        self.session_name.setText(session.name)
        
        self.ocr_panel.load_captures(captures)
        self.speech_panel.load_captures(captures)
        
        if session.summary:
            self.summary_panel.summary.setText(session.summary)
        else:
            self.summary_panel.summary.setPlaceholderText('Press "Summarize" to generate a summary.')