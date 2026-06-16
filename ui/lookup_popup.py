"""Small frameless card shown near the cursor with a translate/define result.

Reused across lookups (created once, re-prepared each time) so there are no
deletion races with the in-flight worker.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence, QGuiApplication

# Grow the result box to fit its content up to this height, then let it scroll.
RESULT_MAX_HEIGHT = 280


class LookupPopup(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Frameless tool window (no taskbar entry); translucent so the inner card's
        # rounded corners show instead of a square window background.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(300)
        self.setMaximumWidth(440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("lookupCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("sectionHeader")
        header.addWidget(self.title_label)
        header.addStretch()
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("Close (Esc)")
        # A fixed red ✕ — clearly visible on both the light and dark card, no theme
        # detection (which proved unreliable for this frameless popup).
        self.close_btn.setStyleSheet(
            "QPushButton { color: #d9534f; background: transparent; border: none;"
            " font-size: 15px; border-radius: 6px; }"
            "QPushButton:hover { color: #ff5f57; }"
        )
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        self.original_label = QLabel("")
        self.original_label.setObjectName("muted")
        self.original_label.setWordWrap(True)
        layout.addWidget(self.original_label)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.result.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.result.setMinimumHeight(60)
        layout.addWidget(self.result)

        footer = QHBoxLayout()
        footer.addStretch()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy)
        footer.addWidget(self.copy_btn)
        layout.addLayout(footer)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)

    def prepare(self, title: str, original: str) -> None:
        """Reset the card for a fresh lookup (loading state)."""
        self.title_label.setText(title)
        self.original_label.setText(original if len(original) <= 140 else original[:140] + "…")
        self.result.setPlainText("…")
        self._fit_result_height()
        self.copy_btn.setEnabled(False)
        self.copy_btn.setText("Copy")

    def set_result(self, text: str) -> None:
        self.result.setPlainText(text)
        self.copy_btn.setEnabled(bool(text))
        self._fit_result_height()

    def set_error(self, message: str) -> None:
        self.result.setPlainText(f"Couldn't complete the request:\n{message}")
        self._fit_result_height()

    def _fit_result_height(self) -> None:
        # Size the result box to its content (up to RESULT_MAX_HEIGHT), then let it
        # scroll. Without this the box collapses to its minimum and long results hide.
        doc = self.result.document()
        width = self.result.viewport().width()
        if width > 0:
            doc.setTextWidth(width)
        content = int(doc.size().height()) + 2 * self.result.frameWidth() + 10
        self.result.setFixedHeight(max(60, min(content, RESULT_MAX_HEIGHT)))
        self.adjustSize()
        self._clamp_to_screen()

    def _clamp_to_screen(self) -> None:
        if not self.isVisible():
            return
        g = self.frameGeometry()
        screen = QGuiApplication.screenAt(g.topLeft()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(g.x(), geo.right() - self.width() - 8)
        y = min(g.y(), geo.bottom() - self.height() - 8)
        self.move(max(x, geo.left() + 8), max(y, geo.top() + 8))

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.result.toPlainText())
        self.copy_btn.setText("Copied")

    def show_at(self, global_pos) -> None:
        """Show just below-right of the cursor, clamped to the screen."""
        self.adjustSize()
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(global_pos.x() + 8, geo.right() - self.width() - 8)
        y = min(global_pos.y() + 8, geo.bottom() - self.height() - 8)
        self.move(max(x, geo.left() + 8), max(y, geo.top() + 8))
        self.show()
        self.raise_()
        self.activateWindow()
