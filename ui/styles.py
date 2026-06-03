from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette

from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'themes'


def get_system_theme() -> str:
    palette = QApplication.instance().palette()
    bg = palette.color(QPalette.ColorRole.Window)
    return "dark" if bg.lightness() < 128 else "light"

def apply_theme(theme: str) -> None:
    if theme == "auto":
        theme = get_system_theme()
    
    # theme = "dark" or "light"
    qss_path = THEMES_DIR / f"{theme}.qss"
    if qss_path.exists():
        QApplication.instance().setStyleSheet(qss_path.read_text())
    else:
        QApplication.instance().setStyleSheet("")