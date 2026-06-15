from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QWidget
from PyQt6.QtCore import Qt
from ui.styles import create_button, load_icon
from qframelesswindow import TitleBar



class ShortcutsDialog(QDialog):
    # (group title, [(key combo, description), ...]) — panel toggles work whenever a
    # session is open, so they're their own group, not lumped under "recording".
    SECTIONS = [
        ("General", [
            ("Ctrl+T",  "New session"),
            ("Ctrl+S",  "Settings"),
            ("Ctrl+D",  "Session properties"),
            ("Ctrl+F",  "Recording panel"),
            ("Shift+4", "Toggle sidebar"),
            ("Esc",     "Close current panel"),
        ]),
        ("Panels", [
            ("Shift+1", "Toggle OCR panel"),
            ("Shift+2", "Toggle Audio panel"),
            ("Shift+3", "Toggle Summary panel"),
        ]),
        ("During Recording", [
            ("Return",      "Stop recording (with confirmation)"),
            ("Ctrl+Return", "Capture now"),
        ]),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(8)

        for idx, (title, rows) in enumerate(self.SECTIONS):
            header = QLabel(title)
            header.setObjectName("sectionHeader")
            # A little extra air above every group except the first.
            header.setContentsMargins(0, 14 if idx else 0, 0, 4)
            layout.addWidget(header)
            layout.addLayout(self._grid(rows))

        layout.addStretch()
        self.setLayout(layout)

    def _grid(self, rows: list[tuple[str, str]]) -> QGridLayout:
        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, 150)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(9)
        for i, (combo, desc) in enumerate(rows):
            grid.addWidget(self._keycaps(combo), i, 0)
            grid.addWidget(QLabel(desc), i, 1)
        return grid

    @staticmethod
    def _keycaps(combo: str) -> QWidget:
        """Render 'Ctrl+T' as separate key-cap chips joined by '+'."""
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        for i, key in enumerate(k.strip() for k in combo.split("+")):
            if i:
                plus = QLabel("+")
                plus.setObjectName("muted")
                row.addWidget(plus)
            cap = QLabel(key)
            cap.setObjectName("kbd")
            row.addWidget(cap)
        row.addStretch()
        return w


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