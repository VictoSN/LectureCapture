from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QWidget, QVBoxLayout,QHBoxLayout
)
from PyQt6.QtCore import Qt, pyqtSignal

class NewSessionPanel(QWidget):
    create_clicked = pyqtSignal(str, str, str)
    cancel_clicked = pyqtSignal()
    
    def __init__(self) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        button_layout = QHBoxLayout()

        # Input Fields
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        main_layout.addWidget(self.session_name)

        self.session_category = QComboBox()
        self.session_category.addItems(["Lab", "Tutorial", "Lecture"])
        main_layout.addWidget(self.session_category)

        self.group_category = QLineEdit()
        self.group_category.setPlaceholderText("Group Category...")
        main_layout.addWidget(self.group_category)

        # Actions Buttons
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_clicked)
        button_layout.addWidget(self.cancel_button)
        
        self.create_button = QPushButton("Create")
        self.create_button.clicked.connect(
            lambda: self.create_clicked.emit(
                self.session_name.text(), 
                self.session_category.currentText(), 
                self.group_category.text() if self.group_category.text().strip() else ""
            ) if self.session_name.text().strip() else None
        )
        button_layout.addWidget(self.create_button)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
                
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_clicked.emit()
        else:
            super().keyPressEvent(event)