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
        self.is_locked = True

        # Header Layout
        speech_label = QLabel("Audio transcript")
        header.addWidget(speech_label)
        self.speech_button = QPushButton("Locked")
        self.speech_button.clicked.connect(self.set_locked)
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

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        capture_widget = QWidget()
        capture_layout = QVBoxLayout()
        
        # Timestamp & Extracted speech text
        capture_timestamp = QLabel(f"{capture.timestamp:.2f}s")
        capture_layout.addWidget(capture_timestamp)
        
        speech_text = QTextEdit()
        speech_text.setPlainText(capture.speech_text or "")
        speech_text.setReadOnly(self.is_locked)
        capture_layout.addWidget(speech_text)
        
        capture_widget.setProperty("capture_id", capture.id)
        capture_widget.setLayout(capture_layout)
        return capture_widget # Return to load and add methods

    def clear_captures(self):
        # Clear out the layout first
        while self.feed_layout.count():
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_captures(self, captures: list[OCRCapture]):
        self.clear_captures()

        for capture in captures:
            self.feed_layout.addWidget(self._create_capture_widget(capture))
            
    def add_capture(self, capture: OCRCapture):
        self.feed_layout.addWidget(self._create_capture_widget(capture))
        
    def update_capture_speech(self, capture_id, text):
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget and widget.property("capture_id") == capture_id:
                text_field = widget.findChild(QTextEdit)
                text_field.setPlainText(text_field.toPlainText() + text)       

    def set_locked(self):
        self.is_locked = not self.is_locked
        self.speech_button.setText("Locked" if self.is_locked else "Editable")
        
        # Lock only the text edit
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(self.is_locked)