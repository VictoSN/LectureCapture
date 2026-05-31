import mss
import sounddevice as sd

from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QDialog, QVBoxLayout,QHBoxLayout, QSpinBox
)
from PyQt6.QtGui import QIntValidator
from PyQt6.QtCore import QSettings, Qt

from ui.set_layout_visible import set_layout_visible

class RecordingDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        capture_layout = QVBoxLayout()
        action_layout = QHBoxLayout()
        int_validator = QIntValidator()

        self.region = None
        self.settings = QSettings("LectureCapture", "LectureCapture")

        self.interval = self.settings.value("interval", 10)
        self.capture_method = self.settings.value("capture_method", "Mouse Select")
        self.region = self.settings.value("region", {
            "left": 0,
            "top": 0,
            "width": 800,
            "height": 800
        })

        # Input Fields
        # Used QSpinBox for integer validation
        self.session_interval = QSpinBox()
        self.session_interval.setRange(1, 30)
        self.session_interval.setValue(int(self.interval))
        main_layout.addWidget(self.session_interval)
        
        ## Control Dropdown
        self.capture_method_dropdown = QComboBox()
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.setCurrentText(self.capture_method)
        self.capture_method_dropdown.currentTextChanged.connect(self.set_user_option)
        capture_layout.addWidget(self.capture_method_dropdown)

        ## Monitor Dropdown
        self.monitor_dropdown = QComboBox()
        self.setup_monitor()
        self.monitor_dropdown.setCurrentText(str(self.settings.value("monitor", "Monitor 1")))
        capture_layout.addWidget(self.monitor_dropdown)

        ## Coords Layout
        self.coords_layout = QHBoxLayout()
        capture_layout.addLayout(self.coords_layout)

        self.x_coords = QLineEdit()
        self.x_coords.setPlaceholderText("X Coordinate")
        self.x_coords.setValidator(int_validator)
        self.x_coords.setText(str(self.region["left"]))
        self.coords_layout.addWidget(self.x_coords)

        self.y_coords = QLineEdit()
        self.y_coords.setPlaceholderText("Y Coordinate")
        self.y_coords.setValidator(int_validator)
        self.y_coords.setText(str(self.region["top"]))
        self.coords_layout.addWidget(self.y_coords)

        self.width_dimension = QLineEdit()
        self.width_dimension.setPlaceholderText("Width")
        self.width_dimension.setValidator(int_validator)
        self.width_dimension.setText(str(self.region["width"]))
        self.coords_layout.addWidget(self.width_dimension)

        self.height_dimension = QLineEdit()
        self.height_dimension.setPlaceholderText("Height")
        self.height_dimension.setValidator(int_validator)
        self.height_dimension.setText(str(self.region["height"]))
        self.coords_layout.addWidget(self.height_dimension)

        self.audio_dropdown = QComboBox()
        self.setup_audio()
        self.audio_dropdown.setCurrentText(str(self.settings.value("audio")))
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
        
        return {
            "interval": self.session_interval.value(),
            "region": self.region,
            "capture_option": self.capture_method,
            "monitor": self.monitor_dropdown.currentData(),
            "audio_device": self.audio_dropdown.currentData()
        }
        
    def setup_monitor(self) -> None:
        self.monitor_dropdown.clear()

        with mss.mss() as sct:
            monitors_with_index = list(enumerate(sct.monitors[1:], 1)) # [(1, {...}), (2, {...})]
            monitors_with_index.sort(key=lambda x: not x[1].get('is_primary', False)) # primary first

            # a tad bit broken, not to mention insane amount of api usage
            # if len(monitors_with_index) > 1:
            #     self.monitor_dropdown.addItem("All Monitor", 0)

            for display_num, (mss_index, m) in enumerate(monitors_with_index, 1):
                self.monitor_dropdown.addItem(
                    f"Monitor {display_num} | {m['width']}x{m['height']} ({m['left']},{m['top']})", mss_index
                )
    
    def setup_audio(self) -> None:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0 and device["hostapi"] == 0:
                self.audio_dropdown.addItem(device["name"], i)
    
    # Hide or Show the user option for screenshots
    def set_user_option(self) -> None:
        self.capture_method = self.capture_method_dropdown.currentText()
        if self.capture_method == "Mouse Select" or self.capture_method == "Full Window":
            set_layout_visible(self.coords_layout, False)
        elif self.capture_method == "Coordinates":
            set_layout_visible(self.coords_layout, True)
    
    def set_error(self, widget, error: bool) -> None:
        widget.setStyleSheet("border: 2px solid red;" if error else "")
    
    def validate(self) -> bool:
        error = False
        monitor_info = None
        with mss.mss() as sct:
            if not self.capture_method == "Mouse Select":
                monitor_info = sct.monitors[self.monitor_dropdown.currentData()]
        
        if not self.session_interval.text().strip():
            error = True
        self.set_error(self.session_interval, error)            

        # Make sure coordinates exist
        if self.capture_method == "Coordinates":
            coords_filled = all([self.x_coords.text(), self.y_coords.text(), self.width_dimension.text(), \
                self.height_dimension.text()])
            
            if not coords_filled:
                error = True
                self.set_error(self.x_coords, not self.x_coords.text())
                self.set_error(self.y_coords, not self.y_coords.text())
                self.set_error(self.width_dimension, not self.width_dimension.text())
                self.set_error(self.height_dimension, not self.height_dimension.text())
            else:
                # Only check bounds if all fields are filled
                # Make sure there are no absurd values
                if int(self.x_coords.text()) + int(self.width_dimension.text()) > monitor_info["width"] or \
                    int(self.y_coords.text()) + int(self.height_dimension.text()) > monitor_info["height"]:
                    error = True
                    self.set_error(self.x_coords, True)
                    self.set_error(self.y_coords, True)
                    self.set_error(self.width_dimension, True)
                    self.set_error(self.height_dimension, True)                
        
        return not error
    
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)