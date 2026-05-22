from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QListWidget, QHBoxLayout
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from storage.database import Storage
from pathlib import Path

from ui.sidebar import Sidebar

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR.parent / 'assets' / 'icon.png'

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()
        
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1000, 700)
        self.setWindowTitle("LectureCapture")
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)
        
        sessions = self.storage.get_all_sessions()
        sidebar = Sidebar(sessions)
        splitter.addWidget(sidebar)
        
        transcript = QWidget()
        transcript.setLayout(QVBoxLayout())
        splitter.addWidget(transcript)
        
        # Wait until the other widgets are added
        splitter.setSizes([100, 400]) # 1 : 4 ratio