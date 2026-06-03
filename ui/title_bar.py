from qframelesswindow import TitleBar
from PyQt6.QtWidgets import QPushButton, QDialog, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        layout = QVBoxLayout()

        shortcuts = [
            ("Ctrl+T", "New Session"),
            ("Ctrl+S", "Settings"),
            ("Ctrl+D", "Properties"),
            ("Ctrl+F", "Start/Cancel Recording"),
            ("Enter", "Stop Recording"),
            ("Shift+1", "Toggle OCR Panel"),
            ("Shift+2", "Toggle Speech Panel"),
            ("Shift+3", "Toggle Summary Panel"),
        ]

        for key, desc in shortcuts:
            layout.addWidget(QLabel(f"{key}  —  {desc}"))

        self.setLayout(layout)

class CustomTitleBar(TitleBar):
    def __init__(self, parent) -> None:
        super().__init__(parent)

        self.title_label = QLabel("LectureCapture")
        self.title_label.setContentsMargins(10, 0, 0, 0)

        self.new_session_button = QPushButton("+")
        self.settings_button = QPushButton("Settings")
        self.help_button = QPushButton("?")
        self.help_button.setFixedSize(30, 30)
        self.help_button.clicked.connect(self._show_shortcuts)
        
        # Insert before the min/max/close buttons
        self.hBoxLayout.insertWidget(0, self.title_label)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.new_session_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.settings_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.help_button)
        
        self.hBoxLayout.setSpacing(10)  
        
    def _show_shortcuts(self) -> None:
        dialog = ShortcutsDialog(self.window())
        dialog.exec()