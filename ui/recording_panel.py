import mss

from PyQt6.QtWidgets import (
    QPushButton, QComboBox, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSpinBox, QLabel
)
from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence

from ui.setup_recording import setup_source, setup_audio, update_coord_ranges

class RecordingPanel(QWidget):
    record_clicked = pyqtSignal(dict)
    cancel_clicked = pyqtSignal()
    
    def __init__(self, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        preferences_layout = QVBoxLayout()
        self.default_layout = QGridLayout()
        action_layout = QHBoxLayout()
        
        self.settings = QSettings("LectureCapture", "LectureCapture")
        self.reload_state()

        # Input Fields
        # Used QSpinBox for integer validation
        
        ## Interval
        self.interval_label = QLabel("Interval:")
        self.default_layout.addWidget(self.interval_label, 0, 0)
        
        self.session_interval = QSpinBox()
        self.session_interval.setRange(1, 30)
        self.default_layout.addWidget(self.session_interval, 0, 1)
        
        ## Capture Method Dropdown
        self.capture_method_label = QLabel("Capture Method:")
        self.default_layout.addWidget(self.capture_method_label, 1, 0)
        
        self.capture_method_dropdown = QComboBox()
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.currentTextChanged.connect(self.set_user_option)
        self.default_layout.addWidget(self.capture_method_dropdown, 1, 1)

        ## Source Dropdown
        self.source_label = QLabel("Source:")
        self.default_layout.addWidget(self.source_label, 2, 0)

        self.source_dropdown = QComboBox()
        setup_source(self.source_dropdown, icons_dir)
        self.default_layout.addWidget(self.source_dropdown, 2, 1)

        ## Coords Layout
        self.x_label = QLabel("X Coordinate:")
        self.default_layout.addWidget(self.x_label, 3, 0)

        self.x_coords = QSpinBox()
        self.default_layout.addWidget(self.x_coords, 3, 1)

        self.y_label = QLabel("Y Coordinate:")
        self.default_layout.addWidget(self.y_label, 4, 0)

        self.y_coords = QSpinBox()
        self.default_layout.addWidget(self.y_coords, 4, 1)

        self.width_label = QLabel("Width:")
        self.default_layout.addWidget(self.width_label, 5, 0)

        self.width_dimension = QSpinBox()
        self.default_layout.addWidget(self.width_dimension, 5, 1)

        self.height_label = QLabel("Height:")
        self.default_layout.addWidget(self.height_label, 6, 0)

        self.height_dimension = QSpinBox()
        self.default_layout.addWidget(self.height_dimension, 6, 1)

        self.source_dropdown.currentIndexChanged.connect(self._on_source_changed)
        self._on_source_changed()

        self.default_container = QWidget()
        self.default_container.setLayout(self.default_layout)
        preferences_layout.addWidget(self.default_container)

        # Audio
        self.audio_label = QLabel("Audio:")
        self.default_layout.addWidget(self.audio_label, 7, 0)

        self.audio_dropdown = QComboBox()
        setup_audio(self.audio_dropdown, icons_dir)
        self.default_layout.addWidget(self.audio_dropdown, 7, 1)        

        # Need to call 'update_coord_ranges' before calling setValue
        self.load_preferences()

        # Actions Buttons
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self._on_cancel)
        action_layout.addWidget(cancel_button)
        
        start_button = QPushButton("Start Recording")
        start_button.clicked.connect(self.try_record)
        action_layout.addWidget(start_button)

        main_layout.addLayout(preferences_layout)
        main_layout.addStretch()
        main_layout.addLayout(action_layout)
        self.setLayout(main_layout)
        
        self.set_user_option()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.try_record)

    def load_preferences(self) -> None:
        self.session_interval.setValue(int(self.interval))
        self.capture_method_dropdown.setCurrentText(self.capture_method)

        idx = self.source_dropdown.findText(self.saved_source)
        self.source_dropdown.setCurrentIndex(idx if idx >= 0 else 0)

        self.x_coords.setValue(int(self.region["left"]))
        self.y_coords.setValue(int(self.region["top"]))
        self.width_dimension.setValue(int(self.region["width"]))
        self.height_dimension.setValue(int(self.region["height"]))

    def _on_source_changed(self) -> None:
        source = self.source_dropdown.currentData()
        if not source:
            return
        if source["type"] == "monitor":
            update_coord_ranges(source["index"], self.x_coords, self.y_coords, self.width_dimension, self.height_dimension)
        else:
            import win32gui
            left, top, right, bottom = win32gui.GetClientRect(source["hwnd"])
            w, h = right, bottom
            self.x_coords.setRange(0, w)
            self.y_coords.setRange(0, h)
            self.width_dimension.setRange(0, w)
            self.height_dimension.setRange(0, h)

    def on_record(self) -> None:
        # Save preferences
        source = self.source_dropdown.currentData()
        self.settings.setValue("interval", self.session_interval.value())
        self.settings.setValue("capture_method", self.capture_method)
        self.settings.setValue("source", self.source_dropdown.currentText())
        self.settings.setValue("audio", self.audio_dropdown.currentText())

        if self.capture_method == "Coordinates":
            # Saved to return
            self.region = {
                "left": int(self.x_coords.text()),
                "top": int(self.y_coords.text()),
                "width": int(self.width_dimension.text()),
                "height": int(self.height_dimension.text())
            }
            # Saved for preferences
            self.settings.setValue("region", self.region)
        elif self.capture_method == "Full Window":
            self.region = None

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
        is_coords = self.capture_method == "Coordinates"

        self.x_label.setVisible(is_coords)
        self.x_coords.setVisible(is_coords)
        self.y_label.setVisible(is_coords)
        self.y_coords.setVisible(is_coords)
        self.width_label.setVisible(is_coords)
        self.width_dimension.setVisible(is_coords)
        self.height_label.setVisible(is_coords)
        self.height_dimension.setVisible(is_coords)
        
    def validate(self) -> bool:
        error = False
        
        # Make sure coordinates not empty
        if self.capture_method == "Coordinates":
            source = self.source_dropdown.currentData()
            coords_filled = all([self.x_coords.text(), self.y_coords.text(), self.width_dimension.text(), self.height_dimension.text()])
            
            if not coords_filled:
                error = True
            else:
                # Only check bounds if all fields are filled
                # Make sure there are no absurd values
                if source["type"] == "monitor":
                    with mss.mss() as sct:
                        monitor_info = sct.monitors[source["index"]]
                    if int(self.x_coords.text()) + int(self.width_dimension.text()) > monitor_info["width"] or \
                        int(self.y_coords.text()) + int(self.height_dimension.text()) > monitor_info["height"]:
                        error = True
                else:
                    import win32gui
                    left, top, right, bottom = win32gui.GetWindowRect(source["hwnd"])
                    w, h = right - left, bottom - top
                    if int(self.x_coords.text()) + int(self.width_dimension.text()) > w or \
                        int(self.y_coords.text()) + int(self.height_dimension.text()) > h:
                        error = True
        return not error
    
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