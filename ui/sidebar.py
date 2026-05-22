from PyQt6.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QLabel, QPushButton
)

from models.lecture import Session

class Sidebar(QWidget):
    def __init__(self, sessions: list[Session], on_new_session, on_session_selected):
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
            
        self.lecture_list.itemClicked.connect(
            lambda item: on_session_selected(self.sessions[self.lecture_list.row(item)])
        )

        main_layout.addLayout(header)
        main_layout.addWidget(self.lecture_list)
        self.setLayout(main_layout)
        
        # Keep the list to pass it to on_session_selected method
        self.sessions = sessions
        
    def refresh(self, sessions: list[Session]):
        self.sessions = sessions # Renew sessions
        self.lecture_list.clear()
        
        for session in sessions:
            self.lecture_list.addItem(session.name)
