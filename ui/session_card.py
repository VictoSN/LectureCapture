from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel
)

from models.lecture import Session
from ui.format_time import FormatTime

class SessionCard(QWidget):
    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        
        main_layout = QHBoxLayout()
        
        strip = QFrame()
        strip.setFixedWidth(3)
        
        session_category = self.session.session_category
        
        # Maybe move this into its own file for modularity?
        if session_category == "Lab":
            strip.setStyleSheet("background-color: #2563EB;")
        elif session_category == "Tutorial":
            strip.setStyleSheet("background-color: #4CAF50;")
        elif session_category == "Lecture":
            strip.setStyleSheet("background-color: #8B5CF6;")
            
        main_layout.addWidget(strip)
        
        name_category_layout = QVBoxLayout()
        main_layout.addLayout(name_category_layout)
        
        name_label = QLabel(self.session.name)
        name_category_layout.addWidget(name_label)
        
        group_category_label = QLabel(self.session.group_category or "")
        name_category_layout.addWidget(group_category_label)
        
        main_layout.addStretch()
        date_modified_label = QLabel(str(FormatTime(self.session.date_modified)))
        main_layout.addWidget(date_modified_label)

        self.setLayout(main_layout)