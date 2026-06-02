from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QWidget, QVBoxLayout,QHBoxLayout, QLabel, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt

from models.lecture import Session
from ui.format_time import FormatDetailedTime

class PropertiesPanel(QWidget):
    delete_clicked = pyqtSignal()
    duplicate_clicked = pyqtSignal()
    saved_clicked = pyqtSignal(str, str, str)
    cancel_clicked = pyqtSignal()

    def __init__(self, session: Session) -> None:
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
        self.delete_button.clicked.connect(self.deleteEvent)
        button_layout.addWidget(self.delete_button)
        
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.clicked.connect(self.duplicate_clicked)
        button_layout.addWidget(self.duplicate_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_clicked)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(
            lambda: self.saved_clicked.emit(
                self.session_name.text(), 
                self.session_category.currentText(), 
                self.group_category.text() if self.group_category.text().strip() else ""
            )
        )
        button_layout.addWidget(self.save_button)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def deleteEvent(self) -> None:
        reply = QMessageBox.question(
            self, 
            "Delete Session", 
            "Delete the current session?"
        )
        if reply == QMessageBox.StandardButton.No:
            return
        else:
            self.delete_clicked.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_clicked.emit()
        else:
            super().keyPressEvent(event)