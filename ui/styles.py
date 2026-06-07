from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QSizePolicy, QPushButton, QToolButton, QApplication
)
from PyQt6.QtCore import Qt, QSize, QSettings
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette

from pathlib import Path

def get_system_theme() -> str:
    palette = QApplication.instance().palette()
    bg = palette.color(QPalette.ColorRole.Window)
    return "dark" if bg.lightness() < 128 else "light"

def apply_theme(theme: str, themes_dir) -> None:
    if theme == "auto":
        theme = get_system_theme()
    
    # theme = "dark" or "light"
    qss_path = themes_dir / f"{theme}.qss"
    if qss_path.exists():
        QApplication.instance().setStyleSheet(qss_path.read_text())
    else:
        QApplication.instance().setStyleSheet("")

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

def load_icon(icon_path: str | Path, theme: str = None) -> QIcon:
    name = Path(icon_path).name
    if name in ("light_mode.svg", "dark_mode.svg", "red_dot.svg"):
        return QIcon(str(icon_path))
    
    if not theme:
        settings = QSettings("LectureCapture", "LectureCapture")    
        dark_mode = check_theme(str(settings.value("theme", "auto")))
    elif theme == "auto":
        dark_mode = check_theme(get_system_theme())
    else:
        dark_mode = check_theme(theme)
    
    pixmap = QPixmap(str(icon_path))
    if not dark_mode:
        return QIcon(pixmap)
    white_pixmap = QPixmap(pixmap.size())
    white_pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(white_pixmap)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(white_pixmap.rect(), QColor("white"))
    painter.end()
    return QIcon(white_pixmap)

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

def create_button(icon_path: str | Path, signal=None, size: int = 30, text: str = "", width: int = None, icon_size: int = 18) -> QPushButton:
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

def create_button_label(icon_path: str | Path, text: str, signal=None, width: int = 100, height: int = 100, icon_size: int = 50) -> QToolButton:
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