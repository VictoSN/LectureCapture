from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence
from ui.category_picker import CategoryPicker, DEFAULT_ACTIVITY_CATEGORIES, merged_activity_categories

class NewSessionPanel(QWidget):
    create_clicked = pyqtSignal(str, str, str)
    cancel_clicked = pyqtSignal()

    def __init__(self, activity_categories: list[str] = None, module_categories: list[str] = None) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 22, 24, 0)
        main_layout.setSpacing(18)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(14)
        grid_layout.setVerticalSpacing(12)

        # Panel Label
        self.panel_title = QLabel("New Session")
        self.panel_title.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(self.panel_title)

        # Input Fields
        session_name_label = QLabel("Session Name:")
        grid_layout.addWidget(session_name_label, 0, 0)

        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        self.session_name.setToolTip("A name for this session, e.g. the lecture topic or date.")
        grid_layout.addWidget(self.session_name, 0, 1)

        activity_category_label = QLabel("Activity Category:")
        grid_layout.addWidget(activity_category_label, 1, 0)

        self.activity_category = CategoryPicker(
            "+ Add new activity category…", "New activity category…",
            tooltip="What kind of session this is (Lecture, Lab, Tutorial…).\n"
                    "Pick one or add your own.",
        )
        grid_layout.addWidget(self.activity_category, 1, 1)

        module_category_label = QLabel("Module Category:")
        grid_layout.addWidget(module_category_label, 2, 0)

        self.module_category = CategoryPicker(
            "+ Add new module category…", "New module category…", include_blank=True,
            tooltip="Which module or course this belongs to (optional).\n"
                    "Used to group and filter sessions in the sidebar.",
        )
        grid_layout.addWidget(self.module_category, 2, 1)

        self.set_categories(activity_categories, module_categories)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()

        # Footer matches the Settings panel layout exactly.
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 8, 0, 12)

        self.status_label = QLabel("")
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self.status_label.setText(""))
        footer.addWidget(self.status_label)
        footer.addStretch()

        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel (Esc)")
        self.cancel_button.clicked.connect(self._on_cancel)
        action_layout.addWidget(self.cancel_button)

        self.create_button = QPushButton("Create")
        self.create_button.setToolTip("Create session (Enter)")
        self.create_button.clicked.connect(self._on_save)
        action_layout.addWidget(self.create_button)

        action_layout.insertStretch(0)
        footer.addLayout(action_layout)
        main_layout.addLayout(footer)
        self.setLayout(main_layout)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_save)

    def set_categories(self, activity_categories: list[str] = None, module_categories: list[str] = None) -> None:
        self.activity_category.set_categories(merged_activity_categories(activity_categories))
        self.module_category.set_categories(module_categories or [])

    def _on_save(self) -> None:
        if not self.session_name.text().strip():
            self._show_status("Please enter a session name.")
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
        self.status_label.setText("")

    def _show_status(self, text: str, duration_ms: int = 3000) -> None:
        self.status_label.setText(text)
        self._status_timer.start(duration_ms)
