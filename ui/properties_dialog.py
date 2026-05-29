from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QDialog, QVBoxLayout,QHBoxLayout, QLabel, QMessageBox
)
from PyQt6.QtCore import pyqtSignal

from models.lecture import Session
from ui.format_time import FormatDetailedTime

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

        self.date_recorded = QLabel(FormatDetailedTime(session.date_recorded))
        main_layout.addWidget(self.date_recorded)

        self.date_modified = QLabel(FormatDetailedTime(session.date_modified))
        main_layout.addWidget(self.date_modified)
        
        self.summary_generated = QLabel(FormatDetailedTime(session.summary_generated_at) or "")
        main_layout.addWidget(self.summary_generated)

        # Actions Buttons
        self.delete_button = QPushButton("Delete")
        button_layout.addWidget(self.delete_button)
        
        self.duplicate_button = QPushButton("Duplicate")
        button_layout.addWidget(self.duplicate_button)
        self.cancel_button = QPushButton("Cancel")
        button_layout.addWidget(self.cancel_button)
        self.save_button = QPushButton("Save")
        button_layout.addWidget(self.save_button)

        self.delete_button.clicked.connect(self.deleteEvent)
        self.duplicate_button.clicked.connect(lambda: (self.duplicate_clicked.emit(), self.reject()))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        
    def get_data(self):
        # accept() will automatically call the method
        return {
            "name": self.session_name.text(),
            "session_category": self.session_category.currentText(),
            "group_category": self.group_category.text() if self.group_category.text().strip() else None
        }
    
    def deleteEvent(self):
        reply = QMessageBox.question(self, "Delete Session",
                            "Delete the current session?")
        if reply == QMessageBox.StandardButton.No:
            return
        else:
            self.delete_clicked.emit()
            self.reject()