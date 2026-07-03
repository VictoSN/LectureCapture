import mss

from PyQt6.QtWidgets import (
    QPushButton, QComboBox, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSpinBox, QLabel
)
from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence

from ui.setup_recording import setup_source, setup_audio, update_ranges_for_source, set_coord_fields_visible
from ui.styles import no_wheel

class RecordingPanel(QWidget):
    record_clicked = pyqtSignal(dict)
    cancel_clicked = pyqtSignal()
    
    def __init__(self, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)
        self.default_layout = QGridLayout()
        self.default_layout.setHorizontalSpacing(14)
        self.default_layout.setVerticalSpacing(12)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.settings = QSettings("LectureCapture", "LectureCapture")
        self.icons_dir = icons_dir
        self.reload_state()

        # Panel Label
        self.recording_name = QLabel("Recording")
        self.recording_name.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(self.recording_name)

        # Input Fields
        # Used QSpinBox for integer validation
        ## Interval
        self.interval_label = QLabel("Interval (s):")
        self.default_layout.addWidget(self.interval_label, 0, 0)

        self.session_interval = QSpinBox()
        self.session_interval.setRange(1, 30)
        self.default_layout.addWidget(self.session_interval, 0, 1)
        interval_tip = ("How often a slide snapshot is taken, in seconds (1–30).\n"
                        "A shorter interval catches more slide changes but makes more captures.")
        self.interval_label.setToolTip(interval_tip)
        self.session_interval.setToolTip(interval_tip)

        ## Capture Method Dropdown
        self.capture_method_label = QLabel("Capture Method:")
        self.default_layout.addWidget(self.capture_method_label, 1, 0)

        self.capture_method_dropdown = QComboBox()
        no_wheel(self.capture_method_dropdown)
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.currentTextChanged.connect(self.set_user_option)
        self.default_layout.addWidget(self.capture_method_dropdown, 1, 1)
        capture_tip = ("What area to capture each interval:\n"
                       "• Mouse Select — drag out a region on screen when recording starts\n"
                       "• Coordinates — a fixed rectangle you set with the X/Y/Width/Height fields\n"
                       "• Full Window — the entire monitor or window chosen as the Source")
        self.capture_method_label.setToolTip(capture_tip)
        self.capture_method_dropdown.setToolTip(capture_tip)

        ## Source Dropdown
        self.source_label = QLabel("Source:")
        self.default_layout.addWidget(self.source_label, 2, 0)

        self.source_dropdown = QComboBox()
        no_wheel(self.source_dropdown)
        setup_source(self.source_dropdown, icons_dir)
        self.default_layout.addWidget(self.source_dropdown, 2, 1)
        source_tip = "The monitor or open window to capture slides from."
        self.source_label.setToolTip(source_tip)
        self.source_dropdown.setToolTip(source_tip)

        ## Coords Layout
        self.x_label = QLabel("X Coordinate:")
        self.default_layout.addWidget(self.x_label, 3, 0)

        self.x_coords = QSpinBox()
        self.default_layout.addWidget(self.x_coords, 3, 1)
        x_tip = "Left edge of the capture rectangle, in pixels from the source's left side."
        self.x_label.setToolTip(x_tip)
        self.x_coords.setToolTip(x_tip)

        self.y_label = QLabel("Y Coordinate:")
        self.default_layout.addWidget(self.y_label, 4, 0)

        self.y_coords = QSpinBox()
        self.default_layout.addWidget(self.y_coords, 4, 1)
        y_tip = "Top edge of the capture rectangle, in pixels from the source's top."
        self.y_label.setToolTip(y_tip)
        self.y_coords.setToolTip(y_tip)

        self.width_label = QLabel("Width:")
        self.default_layout.addWidget(self.width_label, 5, 0)

        self.width_dimension = QSpinBox()
        self.default_layout.addWidget(self.width_dimension, 5, 1)
        width_tip = "Width of the capture rectangle, in pixels."
        self.width_label.setToolTip(width_tip)
        self.width_dimension.setToolTip(width_tip)

        self.height_label = QLabel("Height:")
        self.default_layout.addWidget(self.height_label, 6, 0)

        self.height_dimension = QSpinBox()
        self.default_layout.addWidget(self.height_dimension, 6, 1)
        height_tip = "Height of the capture rectangle, in pixels."
        self.height_label.setToolTip(height_tip)
        self.height_dimension.setToolTip(height_tip)

        self.source_dropdown.currentIndexChanged.connect(self._on_source_changed)
        self._on_source_changed()

        # Audio
        self.audio_label = QLabel("Audio:")
        self.default_layout.addWidget(self.audio_label, 7, 0)

        self.audio_dropdown = QComboBox()
        no_wheel(self.audio_dropdown)
        setup_audio(self.audio_dropdown, icons_dir)
        self.default_layout.addWidget(self.audio_dropdown, 7, 1)
        audio_tip = ("The audio input to record and transcribe. \nA microphone, or a system/"
                     "loopback device to capture what's playing on your computer.")
        self.audio_label.setToolTip(audio_tip)
        self.audio_dropdown.setToolTip(audio_tip)

        # Ranges must be set (via _on_source_changed above) before setValue
        self.load_preferences()

        # Actions Buttons
        cancel_button = QPushButton("Cancel")
        cancel_button.setToolTip("Cancel (Esc)")
        cancel_button.clicked.connect(self._on_cancel)
        action_layout.addWidget(cancel_button)

        start_button = QPushButton("Start Recording")
        start_button.setToolTip("Start recording (Enter)")
        start_button.clicked.connect(self.try_record)
        action_layout.addWidget(start_button)

        action_layout.insertStretch(0)

        main_layout.addLayout(self.default_layout)
        main_layout.addStretch()
        main_layout.addLayout(action_layout)
        self.setLayout(main_layout)
        
        self.set_user_option()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.try_record)

    def _find_source_index(self, saved: str) -> int:
        """Match by app_name stored in item data, falling back to label text."""
        for i in range(self.source_dropdown.count()):
            data = self.source_dropdown.itemData(i) or {}
            if data.get("app_name") == saved:
                return i
        return self.source_dropdown.findText(saved)

    def reload_sources(self) -> None:
        # Re-enumerate monitors/windows and audio devices so the dropdowns reflect
        # what's open right now (called each time the panel is shown).
        setup_source(self.source_dropdown, self.icons_dir)
        setup_audio(self.audio_dropdown, self.icons_dir)

    def load_preferences(self) -> None:
        self.session_interval.setValue(int(self.interval))
        self.capture_method_dropdown.setCurrentText(self.capture_method)

        idx = self._find_source_index(self.saved_source)
        self.source_dropdown.setCurrentIndex(idx if idx >= 0 else 0)

        audio_idx = self.audio_dropdown.findText(self.saved_audio)
        if audio_idx >= 0:
            self.audio_dropdown.setCurrentIndex(audio_idx)

        self.x_coords.setValue(int(self.region["left"]))
        self.y_coords.setValue(int(self.region["top"]))
        self.width_dimension.setValue(int(self.region["width"]))
        self.height_dimension.setValue(int(self.region["height"]))

    def _on_source_changed(self) -> None:
        update_ranges_for_source(self.source_dropdown.currentData(),
                                 self.x_coords, self.y_coords,
                                 self.width_dimension, self.height_dimension)

    def on_record(self) -> None:
        # Save preferences
        source = self.source_dropdown.currentData()
        self.settings.setValue("interval", self.session_interval.value())
        self.settings.setValue("capture_method", self.capture_method)
        src_data = self.source_dropdown.currentData() or {}
        self.settings.setValue("source", src_data.get("app_name", self.source_dropdown.currentText()))
        self.settings.setValue("audio", self.audio_dropdown.currentText())

        if self.capture_method == "Coordinates":
            # Saved to return
            self.region = {
                "left": self.x_coords.value(),
                "top": self.y_coords.value(),
                "width": self.width_dimension.value(),
                "height": self.height_dimension.value()
            }
            # Saved for preferences
            self.settings.setValue("region", self.region)
        elif self.capture_method == "Full Window":
            self.region = None

        self.settings.sync()  # persist last-used choices so they survive a restart
        self.record_clicked.emit({
            "interval": self.session_interval.value(),
            "region": self.region,
            "capture_option": self.capture_method,
            "hwnd": source["hwnd"] if source["type"] == "window" else None,
            "monitor": source["index"] if source["type"] == "monitor" else None,
            "audio_device": self.audio_dropdown.currentData()
        })
        
    # Hide or Show the user option for screenshots
    def set_user_option(self) -> None:
        self.capture_method = self.capture_method_dropdown.currentText()
        set_coord_fields_visible(self, self.capture_method == "Coordinates")
        
    def validate(self) -> bool:
        # The coordinate rectangle must be non-empty and fit inside the chosen
        # source. .value() (not int(.text())) so locale formatting can't break
        # parsing, and it matches what on_record actually records.
        if self.capture_method != "Coordinates":
            return True

        x, y = self.x_coords.value(), self.y_coords.value()
        w, h = self.width_dimension.value(), self.height_dimension.value()
        if w <= 0 or h <= 0:
            return False  # a 0-size region records nothing (every grab fails)

        source = self.source_dropdown.currentData()
        if source["type"] == "monitor":
            with mss.mss() as sct:
                monitor_info = sct.monitors[source["index"]]
            max_w, max_h = monitor_info["width"], monitor_info["height"]
        else:
            import win32gui
            left, top, right, bottom = win32gui.GetWindowRect(source["hwnd"])
            max_w, max_h = right - left, bottom - top
        return x + w <= max_w and y + h <= max_h
    
    def reload_state(self):
        mode = self.settings.value("preferences_mode", "last")

        if mode == "empty":
            self.interval = 0
            self.capture_method = "Mouse Select"
            self.region = {"left": 0, "top": 0, "width": 0, "height": 0}
            self.saved_source = ""
            self.saved_audio = ""
        elif mode == "default":
            self.interval = self.settings.value("default_interval", 10)
            self.capture_method = self.settings.value("default_capture_method", "Mouse Select")
            self.region = self.settings.value("default_region", {"left": 0, "top": 0, "width": 800, "height": 800})
            self.saved_source = self.settings.value("default_source", "")
            self.saved_audio = self.settings.value("default_audio", "")
        else:
            self.interval = self.settings.value("interval", 10)
            self.capture_method = self.settings.value("capture_method", "Mouse Select")
            self.region = self.settings.value("region", {"left": 0, "top": 0, "width": 800, "height": 800})
            self.saved_source = self.settings.value("source", "")
            self.saved_audio = self.settings.value("audio", "")
    
    def try_record(self) -> None:
        if self.validate():
            self.on_record()
    
    def _on_cancel(self) -> None:
        self.reload_state()
        self.load_preferences()
        self.cancel_clicked.emit()