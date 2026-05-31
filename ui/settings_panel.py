from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QSpinBox
)
from PyQt6.QtCore import pyqtSignal, QSettings

from ui.set_layout_visible import set_layout_visible
from ui.setup_monitor import setup_monitor

class SettingsPanel(QWidget):
    record_clicked = pyqtSignal()
    
    def __init__(self, base_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        
        # Processing
        processing_layout = QVBoxLayout()
        processing_button_layout = QHBoxLayout()
        self.api_layout = QGridLayout()
        
        # Themes
        theme_layout = QVBoxLayout()
        theme_buttons_layout = QHBoxLayout()
        
        # Preferences
        preferences_layout = QVBoxLayout()
        preferences_buttons_layout = QHBoxLayout()
        self.default_layout = QGridLayout()
        
        # Sound Effects
        start_sound_layout = QHBoxLayout()
        stop_sound_layout = QHBoxLayout()
        
        # Exports
        export_layout = QHBoxLayout()
        
        self.base_dir = base_dir
        self.settings = QSettings("LectureCapture", "LectureCapture")
        self.local_processing = True
        self.interval = self.settings.value("interval", 10)
        self.capture_method = self.settings.value("capture_method", "Mouse Select")
        self.region = self.settings.value("region", {
            "left": 0,
            "top": 0,
            "width": 800,
            "height": 800
        })

        # Visibility Logic
        self.processing_visibility()

        # Header Layout
        self.settings_name = QLabel("Settings")
        main_layout.addWidget(self.settings_name)

        # API vs Local
        processing_label = QLabel("Processing Location")
        processing_layout.addWidget(processing_label)
        
        self.local_button = QPushButton("Local")
        processing_button_layout.addWidget(self.local_button)
        self.api_button = QPushButton("API")
        processing_button_layout.addWidget(self.api_button)

        ocr_label = QLabel("OCR")
        self.api_layout.addWidget(ocr_label, 0, 0)
        self.ocr_dropdown = QComboBox()
        self.api_layout.addWidget(self.ocr_dropdown, 0, 1)
        processing_layout.addLayout(processing_button_layout)
        
        speech_label = QLabel("Speech-to-Text")
        self.api_layout.addWidget(speech_label, 1, 0)
        self.speech_dropdown = QComboBox()
        self.api_layout.addWidget(self.speech_dropdown, 1, 1)
        
        summarize_label = QLabel("Summarizer")
        self.api_layout.addWidget(summarize_label, 2, 0)
        self.summarize_dropdown = QComboBox()
        self.api_layout.addWidget(self.summarize_dropdown, 2, 1)
        processing_layout.addLayout(self.api_layout)

        # Dark, Light, Auto?
        theme_label = QLabel("Application Theme")
        theme_layout.addWidget(theme_label)
        
        self.auto_button = QPushButton("Automatic")
        theme_buttons_layout.addWidget(self.auto_button)
        self.light_button = QPushButton("Light Theme")
        theme_buttons_layout.addWidget(self.light_button)
        self.dark_button = QPushButton("Dark Theme")
        theme_buttons_layout.addWidget(self.dark_button)
        theme_layout.addLayout(theme_buttons_layout)
        
        # Last used, Set Default, Empty
        preferences_label = QLabel("Recording Preferences")
        preferences_layout.addWidget(preferences_label)
        
        self.last_button = QPushButton("Last Used Options")
        preferences_buttons_layout.addWidget(self.last_button)
        self.default_button = QPushButton("Default Options")
        preferences_buttons_layout.addWidget(self.default_button)
        self.clear_button = QPushButton("Clear Options")
        preferences_buttons_layout.addWidget(self.clear_button)
        preferences_layout.addLayout(preferences_buttons_layout)
        
        ## Interval
        self.interval_label = QLabel("Default Interval")
        self.default_layout.addWidget(self.interval_label, 0, 0)
        
        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 30)
        self.interval_input.setValue(int(self.interval))
        self.default_layout.addWidget(self.interval_input, 0, 1)
        
        ## Control Dropdown
        self.capture_method_label = QLabel("Default Capture Method")
        self.default_layout.addWidget(self.capture_method_label, 1, 0)
        
        self.capture_method_dropdown = QComboBox()
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.setCurrentText(self.capture_method)
        self.default_layout.addWidget(self.capture_method_dropdown, 1, 1)

        ## Monitor Dropdown
        self.monitor_label = QLabel("Default Monitor")
        self.default_layout.addWidget(self.monitor_label, 2, 0)

        self.monitor_dropdown = QComboBox()
        setup_monitor(self.monitor_dropdown)
        self.monitor_dropdown.setCurrentText(str(self.settings.value("monitor", "Monitor 1")))
        self.default_layout.addWidget(self.monitor_dropdown, 2, 1)

        # ## Coords Layout
        # self.coords_layout = QHBoxLayout()
        # capture_layout.addLayout(self.coords_layout)

        # self.x_coords = QLineEdit()
        # self.x_coords.setPlaceholderText("X Coordinate")
        # self.x_coords.setValidator(int_validator)
        # self.x_coords.setText(str(self.region["left"]))
        # self.coords_layout.addWidget(self.x_coords)

        # self.y_coords = QLineEdit()
        # self.y_coords.setPlaceholderText("Y Coordinate")
        # self.y_coords.setValidator(int_validator)
        # self.y_coords.setText(str(self.region["top"]))
        # self.coords_layout.addWidget(self.y_coords)

        # self.width_dimension = QLineEdit()
        # self.width_dimension.setPlaceholderText("Width")
        # self.width_dimension.setValidator(int_validator)
        # self.width_dimension.setText(str(self.region["width"]))
        # self.coords_layout.addWidget(self.width_dimension)

        # self.height_dimension = QLineEdit()
        # self.height_dimension.setPlaceholderText("Height")
        # self.height_dimension.setValidator(int_validator)
        # self.height_dimension.setText(str(self.region["height"]))
        # self.coords_layout.addWidget(self.height_dimension)

        # self.audio_dropdown = QComboBox()
        # self.setup_audio()
        # self.audio_dropdown.setCurrentText(str(self.settings.value("audio")))
        # capture_layout.addWidget(self.audio_dropdown)
        preferences_layout.addLayout(self.default_layout)
        
        # Start & Stop sound effects
        start_sound_label = QLabel("Start Recording Sound Effects")
        start_sound_layout.addWidget(start_sound_label)
        self.start_sound_dropdown = QComboBox()
        start_sound_layout.addWidget(self.start_sound_dropdown)

        stop_sound_label = QLabel("Stop Recording Sound Effects")
        stop_sound_layout.addWidget(stop_sound_label)
        self.stop_sound_dropdown = QComboBox()
        stop_sound_layout.addWidget(self.stop_sound_dropdown)

        # Dropdown that contains all the sessions
        export_label = QLabel("Export Layout")
        export_layout.addWidget(export_label)
        self.export_dropdown = QComboBox()
        export_layout.addWidget(self.export_dropdown)
        self.export_button = QPushButton("Export")
        export_layout.addWidget(self.export_button)

        main_layout.addLayout(processing_layout)
        main_layout.addLayout(theme_layout)
        main_layout.addLayout(preferences_layout)
        main_layout.addLayout(start_sound_layout)
        main_layout.addLayout(stop_sound_layout)
        main_layout.addLayout(export_layout)
        self.setLayout(main_layout)

    def processing_visibility(self) -> None:
        set_layout_visible(self.api_layout, self.local_processing)