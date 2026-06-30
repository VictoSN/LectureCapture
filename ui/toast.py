from PyQt6.QtWidgets import QLabel, QWidget, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation


class Toast(QLabel):
    """A transient notification banner that floats over its parent and auto-dismisses.

    Used for save confirmations and similar feedback. It is styled inline (not via the
    QSS theme) so its success-green / error-red background stays legible in both the
    light and dark themes. The widget is parented to a panel and anchors itself to the
    bottom-centre; call `reposition()` from the parent's resizeEvent to keep it placed.
    """

    SUCCESS = "success"
    ERROR = "error"

    # Background colours per kind; white text reads on both. The error red matches the
    # Danger Zone delete button so failures look consistent across the app.
    _COLOURS = {
        SUCCESS: "#2e7d32",
        ERROR: "#b54b35",
    }

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # The banner is purely informational — never steal clicks from the panel beneath.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Make the widget's QFont bold so fontMetrics() (used to size the banner) matches
        # the bold text the stylesheet renders — otherwise the measured width is too narrow
        # and the message wraps. Keep font-weight in the stylesheet too; both are harmless.
        font = self.font()
        font.setBold(True)
        self.setFont(font)

        # Auto-dismiss timer: fires once after the visible duration, then fades out.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

        # Opacity effect drives both the fade-in on show and the fade-out on dismiss.
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(200)
        self._fade.finished.connect(self._on_fade_finished)
        self._fading_out = False

    def show_message(self, text: str, duration_ms: int = 3000) -> None:
        """Show `text` styled for `kind` (SUCCESS/ERROR) and auto-dismiss after duration_ms."""
        self.setStyleSheet(
            f"background-color: #c15f3c; color: #ffffff; "
            "border-radius: 8px; padding: 8px 8px; font-weight: 600;"
        )
        self.setText(text)
        self.adjustSize()
        self.reposition()

        # Restart cleanly even if a previous toast is still on screen.
        self._fading_out = False
        self._fade.stop()
        self._timer.stop()

        self.setVisible(True)
        self.raise_()
        self._opacity.setOpacity(0.0)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

        self._timer.start(duration_ms)

    # Horizontal padding declared in the stylesheet (10px 16px) — the text needs this
    # much extra room on each side beyond the raw glyph width.
    _H_PADDING = 16

    def reposition(self) -> None:
        """Anchor the banner to the bottom-centre of its parent, sized to fit its text
        on a single line (wrapping only when the message is too long for the panel)."""
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 24
        max_width = max(120, parent.width() - 2 * margin)
        # Width to show the message on one line: glyph advance + the QSS padding on both
        # sides + a little slack. Capped at max_width, beyond which word-wrap kicks in.
        text_w = self.fontMetrics().horizontalAdvance(self.text())
        width = min(text_w + 2 * self._H_PADDING + 8, max_width)
        self.setFixedWidth(width)
        self.adjustSize()  # recompute height for the (possibly wrapped) text at this width
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - margin
        self.move(max(margin, x), max(margin, y))

    def _fade_out(self) -> None:
        self._fading_out = True
        self._fade.stop()
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        # Only hide once the fade-OUT completes (the fade-in also lands here).
        if self._fading_out:
            self.setVisible(False)
            self._fading_out = False
