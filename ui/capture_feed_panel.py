"""Shared chassis of the OCR and Audio transcript feeds (OCRPanel / SpeechPanel):
the header with its icon label and Locked/Editable toggle, the scrollable capture
feed, the debounced per-capture save timer, and the lock/busy handling that keeps
both panels' editability in step.

Subclasses build each capture's row in _create_capture_widget() and emit their own
`<kind>_text_changed` signal from _emit_text_changed().
"""

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QScrollArea, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from models.lecture import OCRCapture
from ui.styles import create_label


class CaptureFeedPanel(QWidget):
    immediate_change = pyqtSignal()
    lookup_requested = pyqtSignal(str, str, str)  # (selected_text, kind, target)

    def __init__(self, base_dir, icons_dir, header_icon: str, header_text: str,
                 lock_tooltip: str, margins: tuple) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(*margins)
        main_layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.base_dir = base_dir
        self.icons_dir = icons_dir
        self.is_locked = True
        self._busy = False  # True while summarizing: editing locked, scroll still works

        label_w, self.header_label = create_label(icons_dir / header_icon, header_text)
        header.addWidget(label_w)
        header.addStretch()

        self.lock_button = QPushButton("Locked")
        self.lock_button.setToolTip(lock_tooltip)
        self.lock_button.clicked.connect(self.set_locked)
        header.addWidget(self.lock_button)

        # Scrollable feed
        self.feed_widget = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_widget)
        self.feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # fixes centering bug
        self.feed_layout.setContentsMargins(2, 2, 6, 2)
        self.feed_layout.setSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.feed_widget)
        self.scroll.setWidgetResizable(True)
        # Reserve the vertical scrollbar permanently. If it toggled on/off as the
        # content height changed, the viewport width would flip-flop and the
        # aspect-ratio images would oscillate (resize loop -> freeze -> crash);
        # both feeds sharing it also keeps paired rows the same viewport width.
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        main_layout.addLayout(header)
        main_layout.addWidget(self.scroll)
        self.setLayout(main_layout)

    # ---- provided by subclasses -----------------------------------------

    def _create_capture_widget(self, capture: OCRCapture) -> QWidget:
        raise NotImplementedError

    def _emit_text_changed(self, capture_id: int, text: str) -> None:
        raise NotImplementedError

    # ---- editing ----------------------------------------------------------

    def _wire_save_timer(self, text_edit: QTextEdit, capture_id: int) -> None:
        """Debounce edits into one saved-text signal per pause in typing."""
        timer = QTimer(text_edit)
        timer.setSingleShot(True)
        text_edit._save_timer = timer
        text_edit.textChanged.connect(self.immediate_change)
        text_edit.textChanged.connect(lambda: timer.start(500))
        timer.timeout.connect(
            lambda cap_id=capture_id, w=text_edit:
                self._emit_text_changed(cap_id, w.toPlainText())
        )

    def set_locked(self) -> None:
        self.is_locked = not self.is_locked
        self.lock_button.setText("Locked" if self.is_locked else "Editable")
        self._apply_read_only()

    def set_busy(self, busy: bool) -> None:
        """Lock editing (and deletion) while a summary is generating. Scrolling and
        the per-capture image toggle stay usable; the lock/edit toggle is disabled
        so the text can't be made editable mid-summary."""
        self._busy = busy
        self.lock_button.setDisabled(busy or not self.has_content())
        self._apply_read_only()
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if not widget:
                continue
            for button in widget.findChildren(QPushButton):
                if button.property("role") == "delete":
                    button.setDisabled(busy)

    def _apply_read_only(self) -> None:
        read_only = self.is_locked or self._busy
        for i in range(self.feed_layout.count()):
            widget = self.feed_layout.itemAt(i).widget()
            if widget:
                text_edit = widget.findChild(QTextEdit)
                if text_edit:
                    text_edit.setReadOnly(read_only)

    # ---- feed management ---------------------------------------------------

    def clear_captures(self) -> None:
        while self.feed_layout.count():
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_captures(self, captures: list[OCRCapture]) -> None:
        self.clear_captures()
        for capture in captures:
            self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.lock_button.setDisabled(not self.has_content())

    def add_capture(self, capture: OCRCapture) -> None:
        self.feed_layout.addWidget(self._create_capture_widget(capture))
        self.lock_button.setDisabled(False)

    def has_content(self) -> bool:
        return self.feed_layout.count() > 0
