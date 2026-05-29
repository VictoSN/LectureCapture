from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QDialog, QVBoxLayout,QHBoxLayout, QLabel
)
from PyQt6.QtCore import pyqtSignal

from models.lecture import Session

class PropertiesDialog(QDialog):
    delete_clicked = pyqtSignal()
    duplicate_clicked = pyqtSignal()
    
    def __init__(self, session: Session):
        super().__init__()
        main_layout = QVBoxLayout()
        button_layout = QHBoxLayout()

        # Input Fields
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        self.session_name.setText(session.name)
        main_layout.addWidget(self.session_name)

        self.session_category = QComboBox()
        self.session_category.addItems(["Lab", "Tutorial", "Lecture"])
        self.session_category.setCurrentText(session.session_category)
        main_layout.addWidget(self.session_category)

        self.group_category = QLineEdit()
        self.group_category.setPlaceholderText("Group Category...")
        self.group_category.setText(session.group_category or "")
        main_layout.addWidget(self.group_category)

        self.date_recorded = QLabel(str(session.date_recorded))
        main_layout.addWidget(self.date_recorded)

        self.date_modified = QLabel(str(session.date_modified))
        main_layout.addWidget(self.date_modified)

        # Actions Buttons
        self.delete_button = QPushButton("Delete")
        button_layout.addWidget(self.delete_button)
        self.duplicate_button = QPushButton("Duplicate")
        button_layout.addWidget(self.duplicate_button)

        self.delete_button.clicked.connect(self.delete_clicked)
        self.duplicate_button.clicked.connect(self.duplicate_clicked)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        
    def get_data(self):
        # accept() will automatically call the method
        return {
            "name": self.session_name.text(),
            "session_category": self.session_category.currentText(),
            "group_category": self.group_category.text() if self.group_category.text().strip() else None
        }