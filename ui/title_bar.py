from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt
from ui.styles import create_button, load_icon
from qframelesswindow import TitleBar


class CustomTitleBar(TitleBar):
    def __init__(self, parent, icons_dir) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Add a few pixels of breathing room above and below the logo/buttons.
        # Add breathing room — buttons stay 46×32 (their icons use hardcoded pixel
        # positions), they naturally centre in the taller bar via the layout.
        self.setFixedHeight(self.height() + 10)
        self.title_logo = QLabel()
        self.title_logo._icon_path = icons_dir / "logo.png"
        self.title_logo.setPixmap(
            load_icon(icons_dir / "logo.png").pixmap(24, 24)
        )
        self.title_logo.setContentsMargins(10, 0, 0, 0)
        self.title_label = QLabel("LectureCapture")

        self.sidebar_button = create_button(icons_dir / 'sidebar.svg', icon_size=20)
        self.sidebar_button.setToolTip("Toggle sidebar (Shift+4)")
        self.new_session_button = create_button(icons_dir / 'plus.svg')
        self.new_session_button.setToolTip("New session (Ctrl+T)")
        self.settings_button = create_button(icons_dir / 'settings.svg')
        self.settings_button.setToolTip("Settings (Ctrl+S)")
        self.help_button = create_button(icons_dir / 'question.svg', icon_size=22)
        self.help_button.setToolTip("Help & guide")

        # Flat, borderless icon buttons in the title bar (filled buttons look heavy here).
        for _btn in (self.sidebar_button, self.new_session_button, self.settings_button, self.help_button):
            _btn.setObjectName("titleBarButton")

        # Insert before the min/max/close buttons
        self.hBoxLayout.insertWidget(0, self.title_logo)
        self.hBoxLayout.insertWidget(1, self.title_label)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.sidebar_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.new_session_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.settings_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.help_button)

        self.hBoxLayout.setSpacing(10)
