from PyQt6.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QLineEdit, QComboBox, QListWidgetItem, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon

from models.lecture import Session
from ui.styles import create_button, load_icon
from ui.session_card import SessionCard

class Sidebar(QWidget):
    new_session_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    
    search_changed = pyqtSignal(str)
    category_filter_changed = pyqtSignal(str)
    group_filter_changed = pyqtSignal(str)
    
    def __init__(self, sessions: list[Session], on_session_selected, group_categories: list[str], icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        header = QVBoxLayout()

        self.session_search = QLineEdit()
        self.session_search.setPlaceholderText("Search")
        self.session_search.textChanged.connect(self.search_changed)
        search_layout.addWidget(self.session_search)
        
        self.session_search.setClearButtonEnabled(True)
        self._search_icon_path = icons_dir / "search.svg"
        self._search_action = self.session_search.addAction(
            load_icon(self._search_icon_path),
            QLineEdit.ActionPosition.LeadingPosition
        )
        
        self.filter_button = create_button(icons_dir / 'filter.svg', self._show_filter)
        search_layout.addWidget(self.filter_button)
        
        self.session_category = QComboBox()
        self.session_category.addItems(["All", "Lab", "Tutorial", "Lecture"])
        self.session_category.currentTextChanged.connect(self.category_filter_changed)
        self.session_category.setVisible(False)
        header.addWidget(self.session_category)
        
        self.group_category = QComboBox()
        self.group_category.addItems(["All"] + group_categories)
        self.group_category.currentTextChanged.connect(self.group_filter_changed)
        self.group_category.setVisible(False)
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

        main_layout.addLayout(search_layout)
        main_layout.addLayout(header)
        main_layout.addWidget(self.lecture_list)
        self.setLayout(main_layout)
        
        # Keep the list to pass it to on_session_selected method
        self.sessions = sessions
        
    def refresh(self, sessions: list[Session], selected_id: int = None) -> None:
        self.sessions = sessions # Renew sessions
        scroll = self.lecture_list.verticalScrollBar().value()
        self.lecture_list.clear()
        
        # List Layout
        for session in sessions:
            item = QListWidgetItem()
            widget = SessionCard(session)
            
            item.setSizeHint(widget.sizeHint())
            self.lecture_list.addItem(item)
            self.lecture_list.setItemWidget(item, widget)
            
            # Reselect the session
            if selected_id and session.id == selected_id:
                self.lecture_list.setCurrentItem(item)
        
        # Go back to the scroll location
        self.lecture_list.verticalScrollBar().setValue(scroll)

    def set_recording_locked(self, locked: bool) -> None:
        self.filter_button.setDisabled(locked)
        self.session_search.setDisabled(locked)
        self.session_category.setDisabled(locked)
        self.group_category.setDisabled(locked)
        self.lecture_list.setDisabled(locked)
    
    def _show_filter(self) -> None:
        current_visibility = self.session_category.isVisible()
        
        self.session_category.setVisible(not current_visibility)
        self.group_category.setVisible(not current_visibility)
        
        if current_visibility:
            self.session_category.setCurrentIndex(0)
            self.group_category.setCurrentIndex(0)

    def refresh_theme(self, theme: str = None) -> None:
        self.session_search.removeAction(self._search_action)
        self._search_action = self.session_search.addAction(
            load_icon(self._search_icon_path, theme),
            QLineEdit.ActionPosition.LeadingPosition
        )