from PyQt6.QtWidgets import (
    QMainWindow, QSplitter
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from storage.database import Storage
from pathlib import Path

from ui.sidebar import Sidebar
from ui.transcript_panel import TranscriptPanel

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR.parent / 'assets' / 'icon.png'

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()
        
        # Window details
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1200, 700)
        self.setWindowTitle("LectureCapture")
        
        # Splitter Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)
        
        sessions = self.storage.get_all_sessions()
        sidebar = Sidebar(sessions, self.on_new_session)
        splitter.addWidget(sidebar)
        
        transcript_panel = TranscriptPanel()
        splitter.addWidget(transcript_panel)
        
        # Wait until the other widgets are added
        splitter.setSizes([100, 400]) # 1 : 4 ratio
        
    def on_new_session(self):
        pass