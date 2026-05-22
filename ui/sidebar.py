from PyQt6.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton
)

from models.lecture import Session

class Sidebar(QWidget):
    def __init__(self, sessions: list[Session], on_new_session ):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QVBoxLayout()
        
        # Header Layout
        lecture_label = QLabel("Lectures")
        header.addWidget(lecture_label)
        
        new_session_button = QPushButton("+ New Session")
        new_session_button.clicked.connect(on_new_session)
        header.addWidget(new_session_button)

        # List Layout
        self.lecture_list = QListWidget()
        for session in sessions:
            self.lecture_list.addItem(session.name)
            
        main_layout.addLayout(header)
        main_layout.addWidget(self.lecture_list)
        self.setLayout(main_layout)