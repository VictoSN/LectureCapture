from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from models.lecture import OCRCapture
from ui.styles import create_label, create_button, NoLeakTextEdit

class SpeechPanel(QWidget):
    speech_text_changed = pyqtSignal(int, str)
    immediate_change = pyqtSignal()
    capture_deleted = pyqtSignal(int)  # capture_id
    
    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.base_dir = base_dir
        self.icons_dir = icons_dir
        self.is_locked = True
        self._busy = False  # True while summarizing: editing locked, scroll still works

        # Header Layout
        speech_w, self.speech_engine_label = create_label(icons_dir / 'microphone.svg', 'Audio transcript')
        header.addWidget(speech_w)
        header.addStretch()

        self.speech_button = QPushButton("Locked")
        self.speech_button.setToolTip("Toggle transcript editing")
        self.speech_button.clicked.connect(self.set_locked)
        header.addWidget(self.speech_button)

        # Scrollable
        self.feed_widget = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_widget)
        self.feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # fixes centering bug
        self.feed_layout.setContentsMargins(2, 2, 6, 2)
        self.feed_layout.setSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.feed_widget)
        self.scroll.setWidgetResizable(True)
        # Keep in lockstep with the OCR panel's always-on scrollbar so paired
        # rows share the same viewport width and stay vertically aligned.
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        main_layout.addLayout(header)
        main_layout.addWidget(self.scroll)
        self.setLayout(main_layout)

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        capture_widget = QWidget()
        capture_layout = QVBoxLayout()

        speech_text = NoLeakTextEdit()
        speech_text.blockSignals(True)
        speech_text.setPlainText(capture.speech_text or "")
        speech_text.blockSignals(False)
        speech_text.setReadOnly(self.is_locked or self._busy)
        
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
        return capture_widget

    def _delete_capture(self, capture_id: int, widget: QWidget) -> None:
        self.feed_layout.removeWidget(widget)
        widget.deleteLater()
        self.capture_deleted.emit(capture_id)
        self.speech_button.setDisabled(not self.has_content())

    def clear_captures(self) -> None:
        while self.feed_layout.count():
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_captures(self, captures: list[OCRCapture]) -> None:
        self.clear_captures()
        for capture in captures:
            self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.speech_button.setDisabled(not self.has_content())

    def add_capture(self, capture: OCRCapture) -> None:
        self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.speech_button.setDisabled(False)
    
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
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(self.is_locked)

    def set_busy(self, busy: bool) -> None:
        """Lock editing while a summary is generating; scrolling stays usable and the
        lock/edit toggle is disabled so the transcript can't be edited mid-summary."""
        self._busy = busy
        self.speech_button.setDisabled(busy or not self.has_content())
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(busy or self.is_locked)

    def has_content(self) -> bool:
        return self.feed_layout.count() > 0