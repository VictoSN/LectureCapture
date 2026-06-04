from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QTextEdit
)
from PyQt6.QtCore import pyqtSignal, QTimer

from models.lecture import OCRCapture

class SpeechPanel(QWidget):
    speech_text_changed =pyqtSignal(int, str)
    immediate_change = pyqtSignal()
    
    def __init__(self, base_dir) -> None:
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
        speech_text.blockSignals(True)
        speech_text.setPlainText(capture.speech_text or "")
        speech_text.blockSignals(False)
        speech_text.setReadOnly(self.is_locked)
        
        # Update after 500ms
        timer = QTimer(speech_text)
        timer.setSingleShot(True)
        speech_text._save_timer = timer
                
        speech_text.textChanged.connect(self.immediate_change)
        speech_text.textChanged.connect(lambda: speech_text._save_timer.start(500))
        
        speech_text._save_timer.timeout.connect(
            lambda cap_id=capture.id, w=speech_text:
                self.speech_text_changed.emit(cap_id, w.toPlainText())
        )
        
        capture_layout.addWidget(speech_text)
        
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
            self.speech_button.setDisabled(False)
        else:
            self.speech_button.setDisabled(True)

    def add_capture(self, capture: OCRCapture) -> None:
        self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.speech_button.setDisabled(False)
    
    # Used to update the current capture text while recording
    def update_capture_speech(self, capture_id, text) -> None:
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget and widget.property("capture_id") == capture_id:
                text_field = widget.findChild(QTextEdit)
                text_field.blockSignals(True)
                text_field.setPlainText(text_field.toPlainText() + text)
                text_field.blockSignals(False)

    def set_locked(self) -> None:
        self.is_locked = not self.is_locked
        self.speech_button.setText("Locked" if self.is_locked else "Editable")
        
        # Lock only the text edit
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(self.is_locked)

    def has_content(self) -> bool:
        return self.feed_layout.count() > 0