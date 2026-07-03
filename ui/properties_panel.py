from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QWidget, QVBoxLayout,QHBoxLayout, QLabel, QMessageBox, QGridLayout
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QShortcut, QKeySequence

from models.lecture import Session
from ui.format_time import FormatDetailedTime
from ui.category_picker import CategoryPicker, DEFAULT_ACTIVITY_CATEGORIES, merged_activity_categories

class PropertiesPanel(QWidget):
    delete_clicked = pyqtSignal()
    duplicate_clicked = pyqtSignal()
    saved_clicked = pyqtSignal(str, str, str)
    cancel_clicked = pyqtSignal()

    def __init__(self, session: Session, activity_categories: list[str] = None, module_categories: list[str] = None) -> None:
        super().__init__()
        self.setObjectName("propertiesPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(14)
        grid_layout.setVerticalSpacing(12)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Panel Label
        self.properties_name = QLabel("Properties")
        self.properties_name.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(self.properties_name)

        # Input Fields
        ## Name
        session_name_label = QLabel("Session Name:")
        grid_layout.addWidget(session_name_label, 0, 0)
        
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText("Session name...")
        self.session_name.setText(session.name or "")
        self.session_name.setToolTip("Rename this session.")
        grid_layout.addWidget(self.session_name, 0, 1)

        ## Activity Category
        activity_category_label = QLabel("Activity Category:")
        grid_layout.addWidget(activity_category_label, 1, 0)

        self.activity_category = CategoryPicker(
            "+ Add new activity category…", "New activity category…",
            tooltip="What kind of session this is (Lecture, Lab, Tutorial…).\n"
                    "Pick one or add your own.",
        )
        self.activity_category.set_categories(
            merged_activity_categories(activity_categories),
            select=session.activity_category or "")
        grid_layout.addWidget(self.activity_category, 1, 1)

        ## Module Category
        module_category_label = QLabel("Module Category:")
        grid_layout.addWidget(module_category_label, 2, 0)

        self.module_category = CategoryPicker(
            "+ Add new module category…", "New module category…", include_blank=True,
            tooltip="Which module or course this belongs to (optional).\n"
                    "Used to group and filter sessions in the sidebar.",
        )
        self.module_category.set_categories(module_categories or [], select=session.module_category or "")
        grid_layout.addWidget(self.module_category, 2, 1)

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

        # Quiz Generated
        quiz_generated_label = QLabel("Quiz Generated:")
        grid_layout.addWidget(quiz_generated_label, 6, 0)

        self.quiz_generated = QLabel(FormatDetailedTime(session.quiz_generated_at) or "None")
        grid_layout.addWidget(self.quiz_generated, 6, 1)

        # Actions Buttons
        self.cancel_button = QPushButton("Close")
        self.cancel_button.setToolTip("Close properties (Esc)")
        self.cancel_button.clicked.connect(self.cancel_clicked)
        button_layout.addWidget(self.cancel_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Delete this session (Ctrl+1)")
        self.delete_button.clicked.connect(self.deleteEvent)
        button_layout.addWidget(self.delete_button)

        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.setToolTip("Duplicate this session (Ctrl+2)")
        self.duplicate_button.clicked.connect(self.duplicateEvent)
        button_layout.addWidget(self.duplicate_button)

        self.save_button = QPushButton("Save")
        self.save_button.setToolTip("Save changes (Enter)")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)

        button_layout.insertStretch(0)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.cancel_clicked.emit)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_save)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=self.deleteEvent)
        QShortcut(QKeySequence("Ctrl+2"), self, activated=self.duplicateEvent)
        
    def duplicateEvent(self) -> None:
        reply = QMessageBox.question(
            self,
            "Duplicate Session",
            "Duplicate the current session?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.duplicate_clicked.emit()

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
        session_cat = self.activity_category.value() or DEFAULT_ACTIVITY_CATEGORIES[0]
        self.saved_clicked.emit(
            self.session_name.text(),
            session_cat,
            self.module_category.value(),
        )