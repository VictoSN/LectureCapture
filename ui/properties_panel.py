from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QWidget, QVBoxLayout,QHBoxLayout, QLabel, QMessageBox, QGridLayout
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QShortcut, QKeySequence

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
        grid_layout = QGridLayout()
        button_layout = QHBoxLayout()

        # Panel Label
        self.properties_name = QLabel("Properties")
        main_layout.addWidget(self.properties_name)

        # Input Fields
        ## Name
        session_name_label = QLabel("Session Name:")
        grid_layout.addWidget(session_name_label, 0, 0)
        
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        grid_layout.addWidget(self.session_name, 0, 1)

        ## Session Category
        session_category_label = QLabel("Session Category:")
        grid_layout.addWidget(session_category_label, 1, 0)

        self.session_category = QComboBox()
        self.session_category.addItems(["Lab", "Tutorial", "Lecture"])
        grid_layout.addWidget(self.session_category, 1, 1)

        ## Group Category
        group_category_label = QLabel("Group Category:")
        grid_layout.addWidget(group_category_label, 2, 0)
        
        self.group_category = QLineEdit()
        self.group_category.setPlaceholderText("Group Category...")
        grid_layout.addWidget(self.group_category, 2, 1)

        # Date Recorded
        date_recorded_label = QLabel("Date Recorded:")
        grid_layout.addWidget(date_recorded_label, 3, 0)

        self.date_recorded = QLabel(FormatDetailedTime(session.date_recorded))
        grid_layout.addWidget(self.date_recorded, 3, 1)

        # Date Modified
        date_modified_label = QLabel("Date Modified:")
        grid_layout.addWidget(date_modified_label, 4, 0)
        
        self.date_modified = QLabel(FormatDetailedTime(session.date_modified))
        grid_layout.addWidget(self.date_modified, 4, 1)
        
        # Summary Generated
        summary_generated_label = QLabel("Summary Generated:")
        grid_layout.addWidget(summary_generated_label, 5, 0)
        
        self.summary_generated = QLabel(FormatDetailedTime(session.summary_generated_at) or "None")
        grid_layout.addWidget(self.summary_generated, 5, 1)

        # Actions Buttons
        self.cancel_button = QPushButton("Close")
        self.cancel_button.clicked.connect(self.cancel_clicked)
        button_layout.addWidget(self.cancel_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.deleteEvent)
        button_layout.addWidget(self.delete_button)
        
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.clicked.connect(self.duplicate_clicked)
        button_layout.addWidget(self.duplicate_button)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.cancel_clicked.emit)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_save)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=self.deleteEvent)
        QShortcut(QKeySequence("Ctrl+2"), self, activated=self.duplicate_clicked.emit)
        
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
    
    def _on_save(self) -> None:
        self.saved_clicked.emit(
            self.session_name.text(), 
            self.session_category.currentText(), 
            self.group_category.text() if self.group_category.text().strip() else ""
        )