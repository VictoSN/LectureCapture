from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QDialog, QVBoxLayout,QHBoxLayout
)

from PyQt6.QtCore import Qt

class NewSessionDialog(QDialog):
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
        button_layout.addWidget(self.cancel_button)
        self.create_button = QPushButton("Create")
        button_layout.addWidget(self.create_button)

        self.create_button.clicked.connect(
            lambda: self.accept() if self.session_name.text().strip() else None
        )
        self.cancel_button.clicked.connect(lambda: self.reject())

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        
    def get_data(self) -> dict[str, str | None]:
        # accept() will automatically call the method
        return {
            "session_name": self.session_name.text(),
            "session_category": self.session_category.currentText(),
            "group_category": self.group_category.text() if self.group_category.text().strip() else None
        }

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)