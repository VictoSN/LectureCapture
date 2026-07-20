from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from PyQt6.QtCore import pyqtSignal

from models.lecture import OCRCapture
from ui.capture_feed_panel import CaptureFeedPanel
from ui.styles import NoLeakTextEdit


class SpeechPanel(CaptureFeedPanel):
    speech_text_changed = pyqtSignal(int, str)

    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__(base_dir, icons_dir, 'microphone.svg', 'Audio transcript',
                         "Toggle transcript editing", (8, 8, 8, 8))
        self.speech_button = self.lock_button  # established name (TranscriptPanel, tests)

    def _emit_text_changed(self, capture_id: int, text: str) -> None:
        self.speech_text_changed.emit(capture_id, text)

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        capture_widget = QWidget()
        capture_layout = QVBoxLayout()

        speech_text = NoLeakTextEdit()
        speech_text.blockSignals(True)
        speech_text.setPlainText(capture.speech_text or "")
        speech_text.blockSignals(False)
        speech_text.setReadOnly(self.is_locked or self._busy)
        speech_text.lookup_requested.connect(self.lookup_requested)

        self._wire_save_timer(speech_text, capture.id)

        capture_layout.addWidget(speech_text)

        # "transcribing…" placeholder, shown while a chunk is being processed.
        pending = QLabel("● transcribing…")
        pending.setObjectName("pendingIndicator")
        pending.setStyleSheet("color: #d97757; font-style: italic; padding: 0 4px;")
        pending.setVisible(False)
        capture_layout.addWidget(pending)

        capture_widget.setProperty("capture_id", capture.id)
        capture_widget.setLayout(capture_layout)
        return capture_widget

    def _find_capture_widget(self, capture_id) -> QWidget | None:
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget and widget.property("capture_id") == capture_id:
                return widget
        return None

    def show_pending(self, capture_id) -> None:
        widget = self._find_capture_widget(capture_id)
        if widget:
            label = widget.findChild(QLabel, "pendingIndicator")
            if label:
                label.setVisible(True)

    def clear_pending(self, capture_id) -> None:
        widget = self._find_capture_widget(capture_id)
        if widget:
            label = widget.findChild(QLabel, "pendingIndicator")
            if label:
                label.setVisible(False)

    def update_capture_speech(self, capture_id, text) -> None:
        widget = self._find_capture_widget(capture_id)
        if widget:
            text_field = widget.findChild(QTextEdit)
            text_field.blockSignals(True)
            text_field.setPlainText(text_field.toPlainText() + text)
            text_field.blockSignals(False)
