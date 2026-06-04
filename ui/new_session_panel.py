from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence

class NewSessionPanel(QWidget):
    create_clicked = pyqtSignal(str, str, str)
    cancel_clicked = pyqtSignal()
    
    def __init__(self) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        grid_layout = QGridLayout()
        button_layout = QHBoxLayout()

        # Panel Label
        self.new_session_name = QLabel("New Session")
        main_layout.addWidget(self.new_session_name)

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

        # Actions Buttons
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)
        
        self.create_button = QPushButton("Create")
        self.create_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.create_button)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_save)
    
    def _on_save(self) -> None:
        self.create_clicked.emit(
            self.session_name.text(), 
            self.session_category.currentText(), 
            self.group_category.text() if self.group_category.text().strip() else ""
        ) if self.session_name.text().strip() else None

    def _on_cancel(self) -> None:
        self.reset_form()
        self.cancel_clicked.emit()

    def reset_form(self):
        self.session_name.clear()
        self.session_category.setCurrentIndex(0)
        self.group_category.clear()