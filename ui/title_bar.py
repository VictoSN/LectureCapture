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
        # refresh_icons() re-renders on theme change using _icon_size (default 14). Set it
        # to match the initial size, otherwise the logo shrinks to 14px when the theme flips.
        self.title_logo._icon_size = 20
        self.title_logo.setPixmap(
            load_icon(icons_dir / "logo.png").pixmap(20, 20)
        )
        self.title_logo.setContentsMargins(16, 0, 0, 0)
        self.title_logo.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.sidebar_button = create_button(icons_dir / 'sidebar.svg', icon_size=20)
        self.sidebar_button.setToolTip("Toggle sidebar (Shift+1)")
        self.new_session_button = create_button(icons_dir / 'plus.svg')
        self.new_session_button.setToolTip("New session (Ctrl+T)")
        self.settings_button = create_button(icons_dir / 'settings.svg')
        self.settings_button.setToolTip("Settings (Ctrl+S)")
        self.help_button = create_button(icons_dir / 'question.svg', icon_size=22)
        self.help_button.setToolTip("Help & guide (Ctrl+G)")

        # Flat, borderless icon buttons in the title bar (filled buttons look heavy here).
        for _btn in (self.sidebar_button, self.new_session_button, self.settings_button, self.help_button):
            _btn.setObjectName("titleBarButton")

        # Insert before the min/max/close buttons
        self.hBoxLayout.insertWidget(0, self.title_logo)
        self.hBoxLayout.insertWidget(1, self.sidebar_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.new_session_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.settings_button)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 3, self.help_button)

        self.hBoxLayout.setSpacing(10)

    def add_panel_buttons(self, buttons) -> None:
        """Host the transcript's OCR / Audio / Summary toggle buttons in the title bar,
        placed between the sidebar button and the session actions. A divider sits just
        before the New Session button to separate the two groups. Called by MainWindow
        once the TranscriptPanel (which owns the buttons) exists."""
        idx = self.hBoxLayout.indexOf(self.sidebar_button) + 1
        for btn in buttons:
            # Match the other title-bar icons: flat, borderless, transparent.
            btn.setObjectName("titleBarButton")
            self.hBoxLayout.insertWidget(idx, btn)
            idx += 1