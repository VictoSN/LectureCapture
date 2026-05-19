from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QListWidget, QHBoxLayout
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from storage.database import Storage
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR.parent / 'assets' / 'icon.png'

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()
        
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(800, 600)
        self.setWindowTitle("LectureCapture")
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)
        
        sidebar = QListWidget()
        splitter.addWidget(sidebar)
        
        transcript = QWidget()
        transcript.setLayout(QHBoxLayout())
        splitter.addWidget(transcript)
        
        # Wait until the other widgets are added
        splitter.setSizes([200, 600])