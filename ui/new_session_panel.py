from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence
from ui.category_picker import CategoryPicker, DEFAULT_ACTIVITY_CATEGORIES

class NewSessionPanel(QWidget):
    create_clicked = pyqtSignal(str, str, str)
    cancel_clicked = pyqtSignal()

    def __init__(self, activity_categories: list[str] = None, module_categories: list[str] = None) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(14)
        grid_layout.setVerticalSpacing(12)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Panel Label
        self.new_session_name = QLabel("New Session")
        self.new_session_name.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(self.new_session_name)

        # Input Fields
        ## Name
        session_name_label = QLabel("Session Name:")
        grid_layout.addWidget(session_name_label, 0, 0)
        
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        self.session_name.setToolTip("A name for this session, e.g. the lecture topic or date.")
        grid_layout.addWidget(self.session_name, 0, 1)

        ## Activity Category
        activity_category_label = QLabel("Activity Category:")
        grid_layout.addWidget(activity_category_label, 1, 0)

        self.activity_category = CategoryPicker(
            "+ Add new activity category…", "New activity category…",
            tooltip="What kind of session this is (Lecture, Lab, Tutorial…).\n"
                    "Pick one or add your own.",
        )
        grid_layout.addWidget(self.activity_category, 1, 1)

        ## Module Category
        module_category_label = QLabel("Module Category:")
        grid_layout.addWidget(module_category_label, 2, 0)

        self.module_category = CategoryPicker(
            "+ Add new module category…", "New module category…", include_blank=True,
            tooltip="Which module or course this belongs to (optional).\n"
                    "Used to group and filter sessions in the sidebar.",
        )
        grid_layout.addWidget(self.module_category, 2, 1)

        self.set_categories(activity_categories, module_categories)

        # Actions Buttons
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel (Esc)")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)

        self.create_button = QPushButton("Create")
        self.create_button.setToolTip("Create session (Enter)")
        self.create_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.create_button)

        button_layout.insertStretch(0)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_save)
    
    def set_categories(self, activity_categories: list[str] = None, module_categories: list[str] = None) -> None:
        # Built-in defaults first, then any custom categories the user has added.
        defaults = DEFAULT_ACTIVITY_CATEGORIES
        merged = defaults + [c for c in (activity_categories or []) if c not in defaults]
        self.activity_category.set_categories(merged)
        self.module_category.set_categories(module_categories or [])

    def _on_save(self) -> None:
        if not self.session_name.text().strip():
            return
        session_cat = self.activity_category.value() or DEFAULT_ACTIVITY_CATEGORIES[0]
        self.create_clicked.emit(
            self.session_name.text(),
            session_cat,
            self.module_category.value(),
        )

    def _on_cancel(self) -> None:
        self.reset_form()
        self.cancel_clicked.emit()

    def reset_form(self):
        self.session_name.clear()
        self.activity_category.set_value("")
        self.module_category.set_value("")