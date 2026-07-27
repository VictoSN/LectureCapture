from PyQt6.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QLineEdit, QComboBox, QListWidgetItem, QHBoxLayout, QMenu
)
from PyQt6.QtCore import pyqtSignal, QSize, Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QIcon
from datetime import datetime, timedelta

from models.lecture import Session
from ui.styles import create_button, load_icon, no_wheel
from ui.session_card import SessionCard

class Sidebar(QWidget):
    new_session_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    session_duplicate_requested = pyqtSignal(int)
    session_delete_requested = pyqtSignal(int)
    
    search_changed = pyqtSignal(str)
    category_filter_changed = pyqtSignal(str)
    module_filter_changed = pyqtSignal(str)
    
    def __init__(self, sessions: list[Session], on_session_selected, activity_categories: list[str], module_categories: list[str], icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(14, 14, 14, 4)
        main_layout.setSpacing(12)
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)
        header = QVBoxLayout()
        header.setSpacing(8)

        self.session_search = QLineEdit()
        self.session_search.setPlaceholderText("Search")
        self.session_search.setToolTip("Search sessions by name")
        # Debounced: each emission triggers a DB query and rebuilds every session
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(
            lambda: self.search_changed.emit(self.session_search.text())
        )
        self.session_search.textChanged.connect(lambda _text: self._search_timer.start())
        search_layout.addWidget(self.session_search)

        self.session_search.setClearButtonEnabled(True)
        self._search_icon_path = icons_dir / "search.svg"
        self._search_action = self.session_search.addAction(
            load_icon(self._search_icon_path),
            QLineEdit.ActionPosition.LeadingPosition
        )

        self._filter_icon_path = icons_dir / 'filter.svg'
        self._reset_icon_path = icons_dir / 'x.svg'
        self.filter_button = create_button(self._filter_icon_path, self._on_filter_button)
        self.filter_button.setToolTip("Filter by category")
        search_layout.addWidget(self.filter_button)

        self.activity_category = QComboBox()
        no_wheel(self.activity_category)
        self.activity_category.setToolTip("Show only sessions of this activity category. “All” shows everything.")
        self.activity_category.addItems(["All"] + [c for c in activity_categories if c])
        self.activity_category.currentTextChanged.connect(self.category_filter_changed)
        self.activity_category.currentTextChanged.connect(self._update_filter_button)
        self.activity_category.setVisible(False)
        header.addWidget(self.activity_category)

        self.module_category = QComboBox()
        no_wheel(self.module_category)
        self.module_category.setToolTip("Show only sessions in this module. “All” shows everything.")
        self.module_category.addItems(["All"] + module_categories)
        self.module_category.currentTextChanged.connect(self.module_filter_changed)
        self.module_category.currentTextChanged.connect(self._update_filter_button)
        self.module_category.setVisible(False)
        header.addWidget(self.module_category)

        # List Layout
        self.lecture_list = QListWidget()
        self._on_session_selected = on_session_selected
        self._populate_list(sessions)
        self.lecture_list.itemClicked.connect(self._on_item_clicked)
        self.lecture_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lecture_list.customContextMenuRequested.connect(self._on_context_menu)
        self._icons_dir = icons_dir

        main_layout.addLayout(search_layout)
        main_layout.addLayout(header)
        main_layout.addWidget(self.lecture_list)
        self.setLayout(main_layout)
        
        # Keep the list to pass it to on_session_selected method
        self.sessions = sessions
        
    def _date_bucket(self, dt: datetime) -> str:
        now = datetime.now().date()
        d = dt.date() if isinstance(dt, datetime) else dt
        if d == now:
            return "Today"
        if d == now - timedelta(days=1):
            return "Yesterday"
        if d >= now - timedelta(days=7):
            return "Last 7 days"
        return "Older"

    _BUCKET_ORDER = ["Today", "Yesterday", "Last 7 days", "Older"]

    def _populate_list(self, sessions: list[Session], selected_id: int = None) -> None:
        self.sessions = sorted(sessions, key=lambda s: s.date_modified, reverse=True)
        self.lecture_list.clear()

        current_bucket = None
        for session in self.sessions:
            bucket = self._date_bucket(session.date_modified)
            if bucket != current_bucket:
                current_bucket = bucket
                header_item = QListWidgetItem(bucket)
                header_item.setFlags(Qt.ItemFlag.NoItemFlags)
                header_item.setData(Qt.ItemDataRole.UserRole, "_header")
                font = QFont()
                font.setPointSize(9)
                font.setBold(True)
                header_item.setFont(font)
                header_item.setSizeHint(QSize(0, 28))
                self.lecture_list.addItem(header_item)

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, session.id)
            widget = SessionCard(session)
            item.setSizeHint(QSize(0, 62))
            self.lecture_list.addItem(item)
            self.lecture_list.setItemWidget(item, widget)

            if selected_id and session.id == selected_id:
                self.lecture_list.setCurrentItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if item.data(Qt.ItemDataRole.UserRole) == "_header":
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        session = next((s for s in self.sessions if s.id == session_id), None)
        if session:
            self._on_session_selected(session)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.lecture_list.itemAt(pos)
        if item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(session_id, int):
            return
        menu = QMenu(self)
        dup_action = menu.addAction(load_icon(self._icons_dir / "plus.svg"), "Duplicate")
        del_action = menu.addAction(load_icon(self._icons_dir / "delete.svg"), "Delete")
        dup_action.triggered.connect(lambda: self.session_duplicate_requested.emit(session_id))
        del_action.triggered.connect(lambda: self.session_delete_requested.emit(session_id))
        menu.exec(self.lecture_list.mapToGlobal(pos))

    def refresh(self, sessions: list[Session], selected_id: int = None) -> None:
        scroll = self.lecture_list.verticalScrollBar().value()
        self._populate_list(sessions, selected_id)
        self.lecture_list.verticalScrollBar().setValue(scroll)

    def update_categories(self, activity_categories: list[str], module_categories: list[str]) -> None:
        """Rebuild filter dropdowns, preserving selections."""
        for combo, values in ((self.activity_category, activity_categories),
                              (self.module_category, module_categories)):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(["All"] + [c for c in values if c])
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def set_recording_locked(self, locked: bool) -> None:
        self.filter_button.setDisabled(locked)
        self.session_search.setDisabled(locked)
        self.activity_category.setDisabled(locked)
        self.module_category.setDisabled(locked)
        self.lecture_list.setDisabled(locked)
    
    def _show_filter(self) -> None:
        current_visibility = self.activity_category.isVisible()

        self.activity_category.setVisible(not current_visibility)
        self.module_category.setVisible(not current_visibility)

        if current_visibility:
            self.activity_category.setCurrentIndex(0)
            self.module_category.setCurrentIndex(0)

    def _is_filter_active(self) -> bool:
        return (self.activity_category.currentText() != "All"
                or self.module_category.currentText() != "All")

    def _on_filter_button(self) -> None:
        # While a filter is applied the button is an ✕ that clears it; otherwise it toggles the category/module dropdowns.
        if self._is_filter_active():
            self.activity_category.setCurrentIndex(0)
            self.module_category.setCurrentIndex(0)
        else:
            self._show_filter()

    def _update_filter_button(self) -> None:
        active = self._is_filter_active()
        path = self._reset_icon_path if active else self._filter_icon_path
        self.filter_button._icon_path = path  # so theme changes recolour the right icon
        self.filter_button.setIcon(load_icon(path))
        self.filter_button.setToolTip("Clear filters" if active else "Filter by category")

    def refresh_theme(self, theme: str = None) -> None:
        self.session_search.removeAction(self._search_action)
        self._search_action = self.session_search.addAction(
            load_icon(self._search_icon_path, theme),
            QLineEdit.ActionPosition.LeadingPosition
        )