from PyQt6.QtWidgets import (
    QListWidget
)

from models.lecture import Session

class Sidebar(QListWidget):
    def __init__(self, sessions: list[Session]):
        super().__init__()
        for session in sessions:
            self.addItem(session.name)