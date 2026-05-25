import mss

from PyQt6.QtWidgets import (
    QPushButton, QLineEdit, QComboBox, QDialog, QVBoxLayout,QHBoxLayout
)
from PyQt6.QtGui import QIntValidator, QGuiApplication

class RecordingDialog(QDialog):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout()
        capture_layout = QVBoxLayout()
        action_layout = QHBoxLayout()
        interval_validator = QIntValidator(1, 30)
        int_validator = QIntValidator()

        self.region = None

        # Input Fields
        self.session_interval = QLineEdit()
        self.session_interval.setPlaceholderText("OCR Interval (Seconds)")
        self.session_interval.setValidator(interval_validator)
        main_layout.addWidget(self.session_interval)
        
        ## Control Dropdown
        self.capture_method_dropdown = QComboBox()
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.currentTextChanged.connect(self.set_user_option)
        capture_layout.addWidget(self.capture_method_dropdown)

        ## Monitor Dropdown
        self.monitor_dropdown = QComboBox()
        self.setup_monitor()
        capture_layout.addWidget(self.monitor_dropdown)

        ## Coords Layout
        self.coords_layout = QHBoxLayout()
        capture_layout.addLayout(self.coords_layout)

        self.x_coords = QLineEdit()
        self.x_coords.setPlaceholderText("X Coordinate")
        self.x_coords.setValidator(int_validator)
        self.coords_layout.addWidget(self.x_coords)

        self.y_coords = QLineEdit()
        self.y_coords.setPlaceholderText("Y Coordinate")
        self.y_coords.setValidator(int_validator)
        self.coords_layout.addWidget(self.y_coords)

        self.width_dimension = QLineEdit()
        self.width_dimension.setPlaceholderText("Width")
        self.width_dimension.setValidator(int_validator)
        self.coords_layout.addWidget(self.width_dimension)

        self.height_dimension = QLineEdit()
        self.height_dimension.setPlaceholderText("Height")
        self.height_dimension.setValidator(int_validator)
        self.coords_layout.addWidget(self.height_dimension)

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

    def get_data(self):
        if self.capture_method == "Coordinates":
            self.region = {
                "left": int(self.x_coords.text()),
                "top": int(self.y_coords.text()),
                "width": int(self.width_dimension.text()),
                "height": int(self.height_dimension.text()),
            }
        elif self.capture_method == "Full Window":
            self.region = None
        
        return {
            "interval": int(self.session_interval.text()),
            "region": self.region,
            "capture_option": self.capture_method,
            "monitor": self.monitor_dropdown.currentData()
        }
        
    # UI Visibility
    def set_layout_visible(self, layout, visible):
        for i in range(layout.count()):
            item = layout.itemAt(i)

            if item.widget():
                if visible:
                    item.widget().show()
                else:
                    item.widget().hide()
            elif item.layout():
                self.set_layout_visible(item.layout(), visible)
        
    def setup_monitor(self):
        if len(QGuiApplication.screens()) > 1:
            self.monitor_dropdown.addItem(f"All Monitor", 0)
            for i in range(1, len(QGuiApplication.screens()) + 1):
                self.monitor_dropdown.addItem(f"Monitor {i}", i)
            return
        self.monitor_dropdown.addItem(f"Monitor 1", 1)
        
    # Hide or Show the user option for screenshots
    def set_user_option(self):
        self.capture_method = self.capture_method_dropdown.currentText()
        if self.capture_method == "Mouse Select" or self.capture_method == "Full Window":
            self.set_layout_visible(self.coords_layout, False)
        elif self.capture_method == "Coordinates":
            self.set_layout_visible(self.coords_layout, True)

        if self.capture_method == "Mouse Select":
            self.monitor_dropdown.hide()
        elif self.capture_method == "Coordinates" or self.capture_method == "Full Window":
            self.monitor_dropdown.show()
    
    def set_error(self, widget, error: bool):
        widget.setStyleSheet("border: 2px solid red;" if error else "")
    
    def validate(self):
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