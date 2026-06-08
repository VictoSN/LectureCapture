from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QGridLayout
from PyQt6.QtCore import Qt
from ui.styles import create_button, load_icon
from qframelesswindow import TitleBar



class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumWidth(380)
        layout = QVBoxLayout()

        # Group: General
        layout.addWidget(self._section("General"))
        general = [
            ("Ctrl+T",  "New Session Panel"),
            ("Ctrl+S",  "Settings Panel"),
            ("Ctrl+D",  "Properties Panel"),
            ("Ctrl+F",  "Recording Panel"),
            ("Shift+4", "Toggle Sidebar"),
            ("Esc",     "Close Panel"),
        ]
        layout.addLayout(self._grid(general))

        # Group: Recording
        layout.addWidget(self._section("During Recording"))
        recording = [
            ("Return",       "Stop Recording (with confirmation)"),
            ("Ctrl+Return", "Force Capture Now"),
            ("Shift+1",           "Toggle OCR Panel"),
            ("Shift+2",           "Toggle Speech Panel"),
            ("Shift+3",           "Toggle Summary Panel"),
        ]
        layout.addLayout(self._grid(recording))

        self.setLayout(layout)

    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(f"<b>{title}</b>")
        label.setContentsMargins(0, 8, 0, 2)
        return label

    @staticmethod
    def _grid(rows: list[tuple[str, str]]) -> QGridLayout:
        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, 170)
        for i, (key, desc) in enumerate(rows):
            key_label = QLabel(key)
            key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(key_label, i, 0)
            grid.addWidget(QLabel("—"), i, 1)
            grid.addWidget(QLabel(desc), i, 2)
        return grid


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
        self.help_button = create_button(icons_dir / 'question.svg', self._show_shortcuts, icon_size=22)
        self.help_button.setToolTip("Keyboard shortcuts")

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

    def _show_shortcuts(self) -> None:
        dialog = ShortcutsDialog(self.window())
        dialog.exec()