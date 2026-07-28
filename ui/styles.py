from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QSizePolicy, QPushButton, QToolButton, QApplication, QTextEdit, QMenu,
    QAbstractScrollArea
)
from PyQt6.QtCore import Qt, QSize, QSettings, QObject, QEvent, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QImage

# Offered in the right-click "Translate to" submenu of any transcript text. The
LOOKUP_LANGUAGES = [
    "Arabic", "Chinese (Simplified)", "French", "German", "Indonesian",
    "Japanese", "Korean", "Malay", "Spanish", "Tamil",
]


class _EatWheelFilter(QObject):
    """Stops the wheel from changing the widget (e.g. a QComboBox), but forwards it to
    an enclosing scroll area so the page still scrolls when the cursor is over it."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            w = obj.parentWidget() if hasattr(obj, "parentWidget") else None
            while w is not None and not isinstance(w, QAbstractScrollArea):
                w = w.parentWidget()
            if w is not None:
                QApplication.sendEvent(w.viewport(), event)
            return True  # never let the widget itself handle the wheel (no value change)
        return False

_eat_wheel_filter: _EatWheelFilter | None = None

def no_wheel(widget) -> None:
    """Prevent mouse-wheel from changing a ComboBox (or any widget)."""
    global _eat_wheel_filter
    if _eat_wheel_filter is None:
        _eat_wheel_filter = _EatWheelFilter(QApplication.instance())
    widget.installEventFilter(_eat_wheel_filter)


_justify_filter: QObject | None = None

class _JustifyFilter(QObject):
    """Global event filter that sets AlignJustify on every QLabel and QTextEdit
    that still has its default (left) alignment.  Widgets with an explicit
    alignment (e.g. AlignCenter for loading messages) are left untouched."""
    _LABEL_DEFAULT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    _TEXTEDIT_DEFAULT = Qt.AlignmentFlag.AlignLeft

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            if isinstance(obj, QLabel):
                if obj.alignment() == self._LABEL_DEFAULT:
                    obj.setAlignment(Qt.AlignmentFlag.AlignJustify | Qt.AlignmentFlag.AlignVCenter)
            elif isinstance(obj, QTextEdit):
                if obj.alignment() == self._TEXTEDIT_DEFAULT:
                    obj.setAlignment(Qt.AlignmentFlag.AlignJustify)
        return False


def install_justify_filter() -> None:
    """Install the global justify-alignment filter on the application."""
    global _justify_filter
    if _justify_filter is None:
        _justify_filter = _JustifyFilter(QApplication.instance())
        QApplication.instance().installEventFilter(_justify_filter)


class NoLeakTextEdit(QTextEdit):
    """QTextEdit that only leaks wheel events to the parent when already at the boundary.

    Scrolling mid-text is contained here. Scrolling past the top/bottom naturally
    continues into the outer panel, so the outer panel is still reachable without
    having to aim at the scrollbar.

    Also adds Define / Translate actions to the right-click menu when text is
    selected, emitting `lookup_requested(selected_text, kind, target)` for a
    controller to act on. kind is "define" or "translate"; target is the language
    for translate ("" => the controller should prompt for a custom one).
    """
    lookup_requested = pyqtSignal(str, str, str)

    def _build_context_menu(self):
        # Built separately from contextMenuEvent so it can be inspected in tests without the blocking menu.exec().
        menu = self.createStandardContextMenu()  # keep Copy / Select All / etc.
        # Standard context-menu icons follow the OS theme; recolour them so they remain
        # visible against the app's light/dark menu background.
        for action in menu.actions():
            if action.icon() and not action.isSeparator():
                action.setIcon(_recolor_icon(action.icon()))
        selected = self.textCursor().selectedText().replace("\u2029", "\n").strip()
        if selected:
            menu.addSeparator()
            short = selected if len(selected) <= 24 else selected[:24] + "…"
            define_act = menu.addAction(f'Define "{short}"')
            define_act.triggered.connect(lambda *_: self.lookup_requested.emit(selected, "define", ""))
            translate_menu = menu.addMenu("Translate to")
            for lang in LOOKUP_LANGUAGES:
                act = translate_menu.addAction(lang)
                act.triggered.connect(lambda *_, l=lang: self.lookup_requested.emit(selected, "translate", l))
            translate_menu.addSeparator()
            other_act = translate_menu.addAction("Other…")
            other_act.triggered.connect(lambda *_: self.lookup_requested.emit(selected, "translate", ""))
        return menu

    def contextMenuEvent(self, event):
        self._build_context_menu().exec(event.globalPos())

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        delta = event.angleDelta().y()
        at_top = bar.value() == bar.minimum()
        at_bottom = bar.value() == bar.maximum()

        # Already at the boundary in the scroll direction → let the outer panel scroll
        if (delta > 0 and at_top) or (delta < 0 and at_bottom):
            event.ignore()
            return

        super().wheelEvent(event)
        event.accept()  # mid-content scroll: consume so it doesn't bleed to the outer panel

from pathlib import Path

def get_system_theme() -> str:
    palette = QApplication.instance().palette()
    bg = palette.color(QPalette.ColorRole.Window)
    return "dark" if bg.lightness() < 128 else "light"

# Dark/light as resolved by the last apply_theme(). load_icon() reads this instead of
_applied_dark: bool | None = None


def apply_theme(theme: str, themes_dir) -> None:
    global _applied_dark
    if theme == "auto":
        theme = get_system_theme()
    _applied_dark = (theme == "dark")

    # theme = "dark" or "light"
    qss_path = themes_dir / f"{theme}.qss"
    if qss_path.exists():
        qss = qss_path.read_text(encoding="utf-8")
        # Resolve url(__ASSETS__/...) image paths to an absolute location so QSS-loaded
        assets = Path(themes_dir).parent.as_posix()
        QApplication.instance().setStyleSheet(qss.replace("__ASSETS__", assets))
    else:
        QApplication.instance().setStyleSheet("")

    # Render rich-text links in the body text colour (Qt underlines them by default)
    app = QApplication.instance()
    palette = app.palette()
    link_color = QColor("#ece7df" if theme == "dark" else "#423f37")
    palette.setColor(QPalette.ColorRole.Link, link_color)
    app.setPalette(palette)

def check_theme(theme: str) -> bool:
    if theme == "dark":
        return True
    elif theme == "light":
        return False
    else:
        return check_theme(get_system_theme())

def refresh_icons(root: QWidget, theme: str = None) -> None:
    for widget in root.findChildren((QPushButton, QToolButton)):
        path = getattr(widget, "_icon_path", None)
        if path:
            widget.setIcon(load_icon(path, theme))
            
    for widget in root.findChildren(QLabel):
        path = getattr(widget, "_icon_path", None)
        if path:
            size = getattr(widget, "_icon_size", 14)
            widget.setPixmap(load_icon(path, theme).pixmap(size, size))

# Recolored icons are identical for a given (path, dark/light) and were being rebuilt
_icon_cache: dict[tuple[str, bool], QIcon] = {}


def _is_dark_mode() -> bool:
    """Return whether the app is currently in dark mode, falling back to the saved setting."""
    if _applied_dark is not None:
        return _applied_dark
    settings = QSettings("LectureCapture", "LectureCapture")
    return check_theme(str(settings.value("theme", "auto")))


def load_icon(icon_path: str | Path, theme: str = None) -> QIcon:
    name = Path(icon_path).name
    if name in ("light_mode.svg", "dark_mode.svg", "red_dot.svg"):
        return QIcon(str(icon_path))

    if not theme:
        dark_mode = _is_dark_mode()
    elif theme == "auto":
        dark_mode = check_theme(get_system_theme())
    else:
        dark_mode = check_theme(theme)

    key = (str(icon_path), dark_mode)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(str(icon_path))
    if not dark_mode:
        icon = QIcon(pixmap)
    else:
        white_pixmap = QPixmap(pixmap.size())
        white_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(white_pixmap)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(white_pixmap.rect(), QColor("white"))
        painter.end()
        icon = QIcon(white_pixmap)

    _icon_cache[key] = icon
    return icon


def _recolor_icon(icon: QIcon, size: int = 16) -> QIcon:
    """Tint a QIcon to the current theme colour (white in dark, dark in light).

    Used for standard icons that do not follow the app's theme (e.g. the system
    icons in QTextEdit's default context menu). Pixel-level recolouring preserves
    the original alpha channel so anti-aliased edges stay smooth and don't turn
    into speckled halos.
    """
    pixmap = icon.pixmap(size, size)
    if pixmap.isNull():
        return icon

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    color = QColor("white") if _is_dark_mode() else QColor("#423f37")
    r, g, b = color.red(), color.green(), color.blue()

    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 0:
                pixel.setRed(r)
                pixel.setGreen(g)
                pixel.setBlue(b)
                image.setPixelColor(x, y, pixel)

    return QIcon(QPixmap.fromImage(image))


def create_label(icon_path: str | Path, text: str) -> tuple[QWidget, QLabel]:
    w = QWidget()
    w.setFixedHeight(20)
    w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    
    icon = QLabel()
    icon._icon_path = icon_path  
    icon.setPixmap(load_icon(icon_path).pixmap(14, 14))
    
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    
    row.addWidget(icon)
    row.addWidget(label)
    return w, label

def create_button(icon_path: str | Path, signal=None, size: int = 34, text: str = "", width: int = None, icon_size: int = 18) -> QPushButton:
    btn = QPushButton(text)
    btn._icon_path = icon_path
    btn.setIcon(load_icon(icon_path))
    btn.setIconSize(QSize(icon_size, icon_size))
    if width:
        btn.setFixedSize(width, size)   # explicit width → honour it
    elif not text:
        btn.setFixedSize(size, size)    # icon-only → square
    else:
        btn.setFixedHeight(size)        # text button → natural width, no min forced
    if signal:
        btn.clicked.connect(signal)
    return btn

def create_button_label(icon_path: str | Path, text: str, signal=None, width: int = 130, height: int = 120, icon_size: int = 60) -> QToolButton:
    btn = QToolButton()
    btn._icon_path = icon_path
    btn.setIcon(load_icon(icon_path))
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setText(text)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    btn.setFixedSize(width, height)
    if signal:
        btn.clicked.connect(signal)
    return btn