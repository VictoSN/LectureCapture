from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton
from PyQt6.QtCore import pyqtSignal, QTimer

from ui.styles import create_label, create_button

class SummaryPanel(QWidget):
    summarize_clicked = pyqtSignal()
    summary_text_changed = pyqtSignal(str)  # new markdown source
    immediate_change = pyqtSignal()

    def __init__(self, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()

        # The summary is edited as raw Markdown *source*. Preview is opt-in via the
        # button below; rendering is read-only so the source is never lost.
        self._is_preview = False
        self._markdown_source = ""
        self._pre_preview_readonly = False

        # Header Layout
        summary_w, self.summarize_engine_label = create_label(icons_dir / 'summarize.svg', 'AI summary')
        header.addWidget(summary_w)

        self.preview_button = QPushButton("Edit")
        self.preview_button.setFixedHeight(30)
        self.preview_button.clicked.connect(self._toggle_preview)
        header.addWidget(self.preview_button)

        self.summary_button = create_button(icons_dir / 'sparkle.svg', self.summarize_clicked, text="Summarize", icon_size=14)
        header.addWidget(self.summary_button)

        # Summary
        self.summary = QTextEdit()

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
        # stashed source while the rendered preview is showing.
        return self._markdown_source if self._is_preview else self.summary.toPlainText()

    def set_summary(self, source: str) -> None:
        # Default to the rendered Markdown preview; the user clicks the button to edit.
        self._markdown_source = source or ""
        self._pre_preview_readonly = self.summary.isReadOnly()
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
            # Preview -> Edit: restore the editable source.
            self.summary.blockSignals(True)
            self.summary.setPlainText(self._markdown_source)
            self.summary.blockSignals(False)
            self.summary.setReadOnly(self._pre_preview_readonly)
            self.preview_button.setText("Edit")  # current mode = Edit
            self._is_preview = False
