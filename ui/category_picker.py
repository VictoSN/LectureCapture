import hashlib

from PyQt6.QtWidgets import QWidget, QComboBox, QLineEdit, QVBoxLayout

from ui.styles import no_wheel

# Always-available activity categories, even before any session uses them.
DEFAULT_ACTIVITY_CATEGORIES = ["Lab", "Tutorial", "Lecture", "Workshop"]


def merged_activity_categories(custom) -> list[str]:
    """The activity-category list every picker shows: built-in defaults first,
    then any custom categories the user has added that aren't already built in."""
    return DEFAULT_ACTIVITY_CATEGORIES + [
        c for c in (custom or []) if c not in DEFAULT_ACTIVITY_CATEGORIES
    ]

# Fixed strip colours for the built-in categories.
CATEGORY_COLORS = {
    "Lab": "#2563EB",       # blue
    "Tutorial": "#4CAF50",  # green
    "Lecture": "#8B5CF6",   # purple
    "Workshop": "#EAB308",  # yellow
}

# Stable colours for user-added categories, derived from name hash. No DB storage needed.
_CUSTOM_CATEGORY_COLORS = [
    "#EC4899",  # pink
    "#14B8A6",  # teal
    "#F97316",  # orange
    "#0EA5E9",  # sky
    "#A855F7",  # violet
    "#84CC16",  # lime
    "#F43F5E",  # rose
    "#06B6D4",  # cyan
]


def category_color(category: str) -> str:
    """Strip colour for an activity category. Built-ins are fixed; a custom category gets
    a stable colour picked from its name. Returns '' for an empty category."""
    if not category:
        return ""
    if category in CATEGORY_COLORS:
        return CATEGORY_COLORS[category]
    digest = hashlib.md5(category.encode("utf-8")).hexdigest()
    return _CUSTOM_CATEGORY_COLORS[int(digest, 16) % len(_CUSTOM_CATEGORY_COLORS)]


class CategoryPicker(QWidget):
    # Stored as the "Add new…" item's data so it can't collide with a real category.
    _ADD_NEW = "\x00__add_new__"

    def __init__(self, add_label: str, new_placeholder: str,
                 include_blank: bool = False, tooltip: str = "", parent=None) -> None:
        super().__init__(parent)
        self._add_label = add_label
        self._include_blank = include_blank

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.combo = QComboBox()
        no_wheel(self.combo)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo)

        self.new_edit = QLineEdit()
        self.new_edit.setPlaceholderText(new_placeholder)
        self.new_edit.setVisible(False)
        layout.addWidget(self.new_edit)

        # Same hint on both parts so hovering the dropdown or the "add new" field helps.
        if tooltip:
            self.combo.setToolTip(tooltip)
            self.new_edit.setToolTip(tooltip)

    def set_categories(self, categories: list[str], select: str | None = None) -> None:
        """Repopulate the dropdown, preserving the current selection unless `select`
        is given (used to seed the value for an existing session)."""
        keep = select if select is not None else self.value()
        self.combo.blockSignals(True)
        self.combo.clear()
        if self._include_blank:
            self.combo.addItem("None", "")      # shown as "None"; value "" = no category
        seen = set()
        for c in categories:
            if c and c not in seen:
                seen.add(c)
                self.combo.addItem(c, c)
        self.combo.addItem(self._add_label, self._ADD_NEW)
        self.combo.blockSignals(False)
        self.set_value(keep)

    def set_value(self, value: str | None) -> None:
        value = value or ""
        self.new_edit.clear()
        if not value:
            self.combo.setCurrentIndex(0)       # blank, or the first real category
            self._on_combo_changed()
            return
        idx = self.combo.findData(value)        # case-sensitive exact match
        if idx < 0:                             # not in the list yet → add it (before "Add new…")
            idx = self.combo.count() - 1
            self.combo.insertItem(idx, value, value)
        self.combo.setCurrentIndex(idx)
        self._on_combo_changed()

    def value(self) -> str:
        """The chosen category: the typed text when 'Add new…' is selected, otherwise
        the selected item (empty string for the blank option)."""
        if self.combo.currentData() == self._ADD_NEW:
            return self.new_edit.text().strip()
        data = self.combo.currentData()
        return (data if data is not None else self.combo.currentText()).strip()

    def _on_combo_changed(self, *_) -> None:
        adding = self.combo.currentData() == self._ADD_NEW
        self.new_edit.setVisible(adding)
        if adding:
            self.new_edit.setFocus()
