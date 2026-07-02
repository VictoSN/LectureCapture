from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel
)

from models.lecture import Session
from ui.format_time import FormatTime
from ui.category_picker import category_color

class SessionCard(QWidget):
    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(8, 10, 8, 10)
        main_layout.setSpacing(10)
        self.setMinimumHeight(58)

        strip = QFrame()
        strip.setFixedWidth(3)
        
        # Built-in categories have fixed colours; custom ones get a stable colour
        # derived from their name (see category_color).
        color = category_color(self.session.activity_category)
        if color:
            strip.setStyleSheet(f"background-color: {color};")

        main_layout.addWidget(strip)
        
        name_category_layout = QVBoxLayout()
        name_category_layout.setSpacing(3)
        main_layout.addLayout(name_category_layout)

        name_label = QLabel(self.session.name)
        name_label.setStyleSheet("font-weight: 600;")
        name_category_layout.addWidget(name_label)

        module_category_label = QLabel(self.session.module_category or "")
        module_category_label.setObjectName("muted")
        name_category_layout.addWidget(module_category_label)

        main_layout.addStretch()
        date_modified_label = QLabel(str(FormatTime(self.session.date_modified)))
        date_modified_label.setObjectName("muted")
        main_layout.addWidget(date_modified_label)

        self.setLayout(main_layout)