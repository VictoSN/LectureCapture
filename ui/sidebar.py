from PyQt6.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QListWidgetItem
)
from PyQt6.QtCore import pyqtSignal

from models.lecture import Session
from ui.session_card import SessionCard

class Sidebar(QWidget):
    search_changed = pyqtSignal(str)
    category_filter_changed = pyqtSignal(str)
    group_filter_changed = pyqtSignal(str)
    
    def __init__(self, sessions: list[Session], on_new_session, on_settings_opened, on_session_selected, group_categories: list[str]) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QVBoxLayout()

        # Header Layout
        lecture_label = QLabel("Lectures")
        header.addWidget(lecture_label)

        self.new_session_button = QPushButton("+ New Session")
        self.new_session_button.clicked.connect(on_new_session)
        header.addWidget(self.new_session_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(on_settings_opened)
        header.addWidget(self.settings_button)

        self.session_search = QLineEdit()
        self.session_search.setPlaceholderText("Search")
        self.session_search.textChanged.connect(self.search_changed)
        header.addWidget(self.session_search)
        
        self.session_category = QComboBox()
        self.session_category.addItems(["All", "Lab", "Tutorial", "Lecture"])
        self.session_category.currentTextChanged.connect(self.category_filter_changed)
        header.addWidget(self.session_category)
        
        self.group_category = QComboBox()
        self.group_category.addItems(["All"] + group_categories)
        self.group_category.currentTextChanged.connect(self.group_filter_changed)
        header.addWidget(self.group_category)

        # List Layout
        self.lecture_list = QListWidget()
        for session in sessions:
            item = QListWidgetItem()
            widget = SessionCard(session)
            
            item.setSizeHint(widget.sizeHint())
            self.lecture_list.addItem(item)
            self.lecture_list.setItemWidget(item, widget)
                
        self.lecture_list.itemClicked.connect(
            lambda item: on_session_selected(self.sessions[self.lecture_list.row(item)])
        )

        main_layout.addLayout(header)
        main_layout.addWidget(self.lecture_list)
        self.setLayout(main_layout)
        
        # Keep the list to pass it to on_session_selected method
        self.sessions = sessions
        
    def refresh(self, sessions: list[Session]) -> None:
        self.sessions = sessions # Renew sessions
        self.lecture_list.clear()
        
        # List Layout
        for session in sessions:
            item = QListWidgetItem()
            widget = SessionCard(session)
            
            item.setSizeHint(widget.sizeHint())
            self.lecture_list.addItem(item)
            self.lecture_list.setItemWidget(item, widget)
                    
    def set_recording_locked(self, locked: bool) -> None:
        self.new_session_button.setDisabled(locked)
        self.session_search.setDisabled(locked)
        self.session_category.setDisabled(locked)
        self.group_category.setDisabled(locked)
        self.lecture_list.setDisabled(locked)