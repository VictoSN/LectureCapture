from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QSplitter, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal

class SettingsPanel(QWidget):
    record_clicked = pyqtSignal()
    
    def __init__(self, base_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        self.base_dir = base_dir

        # Header Layout
        self.session_name = QLabel()
        self.session_name.setText("hello")
        header.addWidget(self.session_name)


        main_layout.addLayout(header)
        self.setLayout(main_layout)
