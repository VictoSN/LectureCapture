from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QTextEdit
)

from models.lecture import OCRCapture

class SpeechPanel(QWidget):
    def __init__(self, base_dir):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir

        # Header Layout
        speech_label = QLabel("Audio transcript")
        header.addWidget(speech_label)
        self.speech_button = QPushButton("Editable")
        header.addWidget(self.speech_button)

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
            
            # Timestamp & Extracted speech text
            capture_timestamp = QLabel(f"{capture.timestamp:.2f}s")
            capture_layout.addWidget(capture_timestamp)
            
            speech_text = QTextEdit(capture.speech_text)
            capture_layout.addWidget(speech_text)
            
            capture_widget.setLayout(capture_layout)
            self.feed_layout.addWidget(capture_widget)