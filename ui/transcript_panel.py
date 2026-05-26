from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QSplitter, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt, pyqtSignal

from models.lecture import Session, OCRCapture
from ui.ocr_panel import OCRPanel
from ui.speech_panel import SpeechPanel
from ui.summary_panel import SummaryPanel

class TranscriptPanel(QWidget):
    record_clicked = pyqtSignal()
    
    def __init__(self, base_dir, on_properties_clicked):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir

        # Header Layout
        self.session_name = QLabel()
        self.session_name.setText("Session name...")
        header.addWidget(self.session_name)

        self.properties_button = QPushButton("Properties")
        self.properties_button.clicked.connect(on_properties_clicked)
        header.addWidget(self.properties_button)
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
        self.set_session_locked(True)

    def load_session(self, session: Session, captures: OCRCapture):
        self.set_session_locked(False)
        self.session_name.setText(session.name)
        
        self.ocr_panel.load_captures(captures)
        self.speech_panel.load_captures(captures)
        
        if session.summary:
            self.summary_panel.summary.setText(session.summary)
        else:
            self.summary_panel.summary.clear()
            self.summary_panel.summary.setPlaceholderText('Press "Summarize" to generate a summary.')
            
    def set_session_locked(self, locked: bool):
        self.session_name.setDisabled(locked)
        self.properties_button.setDisabled(locked)
        self.ocr_visibility_button.setDisabled(locked)
        self.speech_visibility_button.setDisabled(locked)
        self.summary_visibility_button.setDisabled(locked)
        self.record_button.setDisabled(locked)
        
        self.ocr_panel.ocr_button.setDisabled(locked)
        self.speech_panel.speech_button.setDisabled(locked)
        self.summary_panel.summary_button.setDisabled(locked)

    def set_properties_locked(self, locked: bool):
        self.properties_button.setDisabled(locked)