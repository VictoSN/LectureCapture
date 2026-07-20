from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal, QTimer
from PyQt6.QtGui import QTextCharFormat, QTextCursor

from core.summarizer import strip_code_fence
from ui.styles import create_label, create_button, NoLeakTextEdit

class SummaryPanel(QWidget):
    summarize_clicked = pyqtSignal()
    summary_text_changed = pyqtSignal(str)  # new markdown source
    immediate_change = pyqtSignal()
    lookup_requested = pyqtSignal(str, str, str)  # (selected_text, kind, target)

    def __init__(self, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 10, 8)
        main_layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(8)

        # Summary is edited as raw Markdown source. Preview is opt-in.
        self._is_preview = False
        self._markdown_source = ""
        self._pre_preview_readonly = False

        # Header Layout
        summary_w, self.summarize_engine_label = create_label(icons_dir / 'summarize.svg', 'AI summary')
        header.addWidget(summary_w)
        header.addStretch()

        self.preview_button = QPushButton("Edit")
        self.preview_button.setFixedHeight(30)
        self.preview_button.setToolTip("Toggle Markdown preview")
        self.preview_button.clicked.connect(self._toggle_preview)
        header.addWidget(self.preview_button)

        self.summary_button = create_button(icons_dir / 'sparkle.svg', self.summarize_clicked, text="Summarize", icon_size=14)
        self.summary_button.setToolTip("Generate AI summary from OCR and audio content")
        header.addWidget(self.summary_button)

        # Summary
        self.summary = NoLeakTextEdit()
        self.summary.lookup_requested.connect(self.lookup_requested)

        timer = QTimer(self.summary)
        timer.setSingleShot(True)
        self.summary._save_timer = timer

        self.summary.textChanged.connect(self.immediate_change)
        self.summary.textChanged.connect(lambda: self.summary._save_timer.start(500))
        self.summary._save_timer.timeout.connect(
            lambda: self.summary_text_changed.emit(self.current_source())
        )

        main_layout.addLayout(header)
        main_layout.addWidget(self.summary, stretch=1)
        self.setLayout(main_layout)

    def current_source(self) -> str:
        # The canonical Markdown source: the editor text in edit mode, or the
        return self._markdown_source if self._is_preview else self.summary.toPlainText()

    def set_summary(self, source: str) -> None:
        # Strip any all-enclosing ```markdown fence, or QTextEdit renders as literal code.
        self._markdown_source = strip_code_fence(source or "")
        # A set summary always has content, so edit mode is editable. Don't capture the
        self._pre_preview_readonly = False
        self._is_preview = True
        self.preview_button.setText("Preview")  # current mode = Preview
        self.summary.blockSignals(True)
        self.summary.setMarkdown(self._markdown_source)
        self.summary.blockSignals(False)
        self.summary.setReadOnly(True)

    def clear_summary(self) -> None:
        self._markdown_source = ""
        self._is_preview = False
        self.preview_button.setText("Edit")  # current mode = Edit
        self.summary.blockSignals(True)
        self.summary.clear()
        self.summary.setPlaceholderText('Press "Summarize" to generate a summary.')
        self.summary.blockSignals(False)

    def _toggle_preview(self) -> None:
        if not self._is_preview:
            # Edit -> Preview: stash the source and render it read-only.
            self._markdown_source = self.summary.toPlainText()
            self._pre_preview_readonly = self.summary.isReadOnly()
            self.summary.blockSignals(True)
            self.summary.setMarkdown(self._markdown_source)
            self.summary.blockSignals(False)
            self.summary.setReadOnly(True)
            self.preview_button.setText("Preview")  # current mode = Preview
            self._is_preview = True
        else:
        # Strip character formatting when switching from preview back to edit mode.
            self.summary.blockSignals(True)
            self.summary.setReadOnly(False)
            self.summary.setPlainText(self._markdown_source)
            cursor = self.summary.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.setCharFormat(QTextCharFormat())
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.summary.setTextCursor(cursor)
            self.summary.setCurrentCharFormat(QTextCharFormat())
            self.summary.blockSignals(False)
            self.summary.setReadOnly(self._pre_preview_readonly)
            self.preview_button.setText("Edit")  # current mode = Edit
            self._is_preview = False
