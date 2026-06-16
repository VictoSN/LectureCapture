"""Small frameless card shown near the cursor with a translate/define result.

Reused across lookups (created once, re-prepared each time) so there are no
deletion races with the in-flight worker.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget, QApplication
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QShortcut, QKeySequence, QGuiApplication

from ui.styles import load_icon

# Grow the result box to fit its content up to this height, then let it scroll.
RESULT_MAX_HEIGHT = 280
# The selected/original text grows to fit up to this height, then scrolls so long
# selections (e.g. a whole paragraph) can be reviewed against the translation.
ORIGINAL_MAX_HEIGHT = 96


class LookupPopup(QDialog):
    def __init__(self, parent=None, icons_dir=None) -> None:
        super().__init__(parent)
        self._icons_dir = (
            Path(icons_dir) if icons_dir
            else Path(__file__).resolve().parent.parent / "assets" / "icons"
        )
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
        self.close_btn = QPushButton()
        # The ✕ icon is black in light mode and white in dark mode: load_icon tints it
        # to the active theme, and _icon_path lets refresh_icons re-tint on theme change.
        self.close_btn._icon_path = self._icons_dir / "x.svg"
        self.close_btn.setIcon(load_icon(self.close_btn._icon_path))
        self.close_btn.setIconSize(QSize(14, 14))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("Close (Esc)")
        self.close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(140, 140, 140, 0.20); }"
        )
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        # Read-only view of the selected text. Styled (via #lookupOriginal QSS) to look
        # like muted plain text, but it scrolls once the selection is tall.
        self.original_view = QTextEdit()
        self.original_view.setObjectName("lookupOriginal")
        self.original_view.setReadOnly(True)
        self.original_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.original_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.original_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.original_view)

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
        self.original_view.setPlainText(original)
        self._fit_original_height()
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

    def _fit_original_height(self) -> None:
        # Size the selected-text box to its content (up to ORIGINAL_MAX_HEIGHT), then let
        # it scroll. Short selections stay compact; long ones become scrollable.
        doc = self.original_view.document()
        width = self.original_view.viewport().width()
        if width <= 0:  # not shown yet — estimate from the card width so wrapping is right
            width = self.maximumWidth() - 2 * 14 - 4
        doc.setTextWidth(width)
        content = int(doc.size().height()) + 2 * self.original_view.frameWidth() + 6
        self.original_view.setFixedHeight(max(24, min(content, ORIGINAL_MAX_HEIGHT)))

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
        # Now that it has a real width, re-fit the selected-text box and reposition.
        self._fit_original_height()
        self.adjustSize()
        self._clamp_to_screen()
        self.raise_()
        self.activateWindow()
