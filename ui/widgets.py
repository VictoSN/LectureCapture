from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QSizePolicy, QPushButton
)
from PyQt6.QtGui import  QIcon
from PyQt6.QtCore import Qt, QSize

from pathlib import Path

def create_label(icon_path: str, text: str, icons_dir: Path) -> tuple[QWidget, QLabel]:
    w = QWidget()
    w.setFixedHeight(20)
    w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    
    icon = QLabel()
    icon.setPixmap(QIcon(str(icons_dir / icon_path)).pixmap(14, 14))
    
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    
    row.addWidget(icon)
    row.addWidget(label)
    return w, label

def create_button(icon_path: str, icons_dir: Path, signal=None, size: int = 30, text: str = "", width: int = None, icon_size: int = 18) -> QPushButton:
    btn = QPushButton(text)
    btn.setIcon(QIcon(str(icons_dir / icon_path)))
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setFixedSize(width or size, size)
    if signal:
        btn.clicked.connect(signal)
    return btn