from PyQt6.QtWidgets import (
    QMainWindow, QSplitter
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from models.lecture import Session
from storage.database import Storage
from pathlib import Path
from datetime import datetime

from ui.sidebar import Sidebar
from ui.transcript_panel import TranscriptPanel
from ui.new_session_dialog import NewSessionDialog

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR.parent / 'assets' / 'icon.png'

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()

        # Window details
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1100, 700)
        self.setWindowTitle("LectureCapture")

        # Splitter Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        sessions = self.storage.get_all_sessions()
        self.sidebar = Sidebar(sessions, self.on_new_session, self.on_session_selected)
        splitter.addWidget(self.sidebar)

        self.transcript_panel = TranscriptPanel()
        splitter.addWidget(self.transcript_panel)

        # Wait until the other widgets are added
        splitter.setSizes([100, 400]) # 1 : 4 ratio

    def on_new_session(self):
        dialog = NewSessionDialog()
        
        # Exec blocks until dialog is closed (accepted/cancelled)
        if dialog.exec():
            # Used data to build a new session
            data = dialog.get_data() 
            current_time = datetime.now()
            print(data)
            
            # Create new session using gathered data
            new_session = Session(data["session_name"], current_time, current_time, data["session_category"], 0, None, data["group_category"], None, None)
            self.storage.create_session(new_session)
            self.sidebar.refresh(self.storage.get_all_sessions())
    
    def on_session_selected(self, session: Session):
        captures = self.storage.get_captures_by_session(session.id)
        self.transcript_panel.load_session(session, captures)