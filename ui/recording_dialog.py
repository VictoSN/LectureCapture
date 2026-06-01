import mss

from PyQt6.QtWidgets import (
    QPushButton, QComboBox, QDialog, QVBoxLayout,QHBoxLayout, QSpinBox
)
from PyQt6.QtCore import QSettings, Qt

from ui.set_layout_visible import set_layout_visible
from ui.setup_recording import setup_monitor, setup_audio, update_coord_ranges, setup_window

class RecordingDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        capture_layout = QVBoxLayout()
        action_layout = QHBoxLayout()

        self.settings = QSettings("LectureCapture", "LectureCapture")
        mode = self.settings.value("preferences_mode", "last")
        
        if mode == "empty":
            self.interval = 0
            self.capture_method = "Mouse Select"
            self.region = {"left": 0, "top": 0, "width": 0, "height": 0}
            saved_window = ""
            saved_monitor = "Monitor 1"
            saved_audio = ""
        elif mode == "default":
            self.interval = self.settings.value("default_interval", 10)
            self.capture_method = self.settings.value("default_capture_method", "Mouse Select")
            self.region = self.settings.value("default_region", {"left": 0, "top": 0, "width": 800, "height": 800})
            saved_window = self.settings.value("default_window", "")
            saved_monitor = self.settings.value("default_monitor", "Monitor 1")
            saved_audio = self.settings.value("default_audio", "")
        else:
            self.interval = self.settings.value("interval", 10)
            self.capture_method = self.settings.value("capture_method", "Mouse Select")
            self.region = self.settings.value("region", {"left": 0, "top": 0, "width": 800, "height": 800})
            saved_window = self.settings.value("window", "")
            saved_monitor = self.settings.value("monitor", "Monitor 1")
            saved_audio = self.settings.value("audio", "")

        # Input Fields
        # Used QSpinBox for integer validation
        self.session_interval = QSpinBox()
        self.session_interval.setRange(1, 30)
        self.session_interval.setValue(int(self.interval))
        main_layout.addWidget(self.session_interval)
        
        ## Control Dropdown
        self.capture_method_dropdown = QComboBox()
        self.capture_method_dropdown.addItems(["Mouse Select", "Window Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.setCurrentText(self.capture_method)
        self.capture_method_dropdown.currentTextChanged.connect(self.set_user_option)
        capture_layout.addWidget(self.capture_method_dropdown)

        # Window Dropdown
        self.window_dropdown = QComboBox()
        setup_window(self.window_dropdown)
        self.window_dropdown.setCurrentText(saved_window)
        capture_layout.addWidget(self.window_dropdown)

        ## Monitor Dropdown
        self.monitor_dropdown = QComboBox()
        setup_monitor(self.monitor_dropdown)
        self.monitor_dropdown.setCurrentText(saved_monitor)
        capture_layout.addWidget(self.monitor_dropdown)

        ## Coords Layout
        self.coords_layout = QHBoxLayout()
        capture_layout.addLayout(self.coords_layout)

        self.x_coords = QSpinBox()
        self.coords_layout.addWidget(self.x_coords)

        self.y_coords = QSpinBox()
        self.coords_layout.addWidget(self.y_coords)

        self.width_dimension = QSpinBox()
        self.coords_layout.addWidget(self.width_dimension)

        self.height_dimension = QSpinBox()
        self.coords_layout.addWidget(self.height_dimension)

        self.monitor_dropdown.currentIndexChanged.connect(
            lambda: update_coord_ranges(self.monitor_dropdown.currentData(), self.x_coords, self.y_coords, self.width_dimension, self.height_dimension)
        )
        update_coord_ranges(self.monitor_dropdown.currentData(), self.x_coords, self.y_coords, self.width_dimension, self.height_dimension)

        # Need to call 'update_coord_ranges' before calling setValue
        self.x_coords.setValue(int(self.region["left"]))
        self.y_coords.setValue(int(self.region["top"]))
        self.width_dimension.setValue(int(self.region["width"]))
        self.height_dimension.setValue(int(self.region["height"]))
        
        self.audio_dropdown = QComboBox()
        setup_audio(self.audio_dropdown)
        self.audio_dropdown.setCurrentText(saved_audio)
        capture_layout.addWidget(self.audio_dropdown)

        # Actions Buttons
        cancel_button = QPushButton("Cancel")
        action_layout.addWidget(cancel_button)
        start_button = QPushButton("Start Recording")
        action_layout.addWidget(start_button)

        start_button.clicked.connect(
            lambda: self.accept() if self.validate() else None
        )
        cancel_button.clicked.connect(lambda: self.reject())

        main_layout.addLayout(capture_layout)
        main_layout.addLayout(action_layout)
        self.setLayout(main_layout)
        
        self.set_user_option()

    def get_data(self) -> dict[str, object]:
        # Save preferences
        self.settings.setValue("interval", self.session_interval.value())
        self.settings.setValue("capture_method", self.capture_method)
        self.settings.setValue("monitor", self.monitor_dropdown.currentText())
        self.settings.setValue("audio", self.audio_dropdown.currentText())

        if self.capture_method == "Window Select":
            self.settings.setValue("window", self.window_dropdown.currentText())
        elif self.capture_method == "Coordinates":
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
        
        return {
            "interval": self.session_interval.value(),
            "region": self.region,
            "capture_option": self.capture_method,
            "window": self.window_dropdown.currentData() if self.capture_method == "Window Select" else None,
            "monitor": self.monitor_dropdown.currentData() if self.capture_method != "Window Select" else None,
            "audio_device": self.audio_dropdown.currentData()
        }
                
    # Hide or Show the user option for screenshots
    def set_user_option(self) -> None:
        self.capture_method = self.capture_method_dropdown.currentText()
        is_coords = self.capture_method == "Coordinates"
        is_window = self.capture_method == "Window Select"
        
        # Control the visibility of layouts
        set_layout_visible(self.coords_layout, is_coords)
        self.window_dropdown.setVisible(is_window)
        self.monitor_dropdown.setVisible(not is_window)
            
    def validate(self) -> bool:
        error = False
        
        # Make sure coordinates not empty
        if self.capture_method == "Coordinates":
            monitor_info = None
            with mss.mss() as sct:
                monitor_info = sct.monitors[self.monitor_dropdown.currentData()]
                
            coords_filled = all([self.x_coords.text(), self.y_coords.text(), self.width_dimension.text(), \
                self.height_dimension.text()])
            
            if not coords_filled:
                error = True
            else:
                # Only check bounds if all fields are filled
                # Make sure there are no absurd values
                if int(self.x_coords.text()) + int(self.width_dimension.text()) > monitor_info["width"] or \
                    int(self.y_coords.text()) + int(self.height_dimension.text()) > monitor_info["height"]:
                    error = True
        
        return not error
    
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)