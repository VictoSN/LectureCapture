from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout
)
from PyQt6.QtCore import pyqtSignal

from ui.set_layout_visible import set_layout_visible

class SettingsPanel(QWidget):
    record_clicked = pyqtSignal()
    
    def __init__(self, base_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        
        # Processing
        processing_layout = QVBoxLayout()
        processing_button_layout = QHBoxLayout()
        processing_layout.addLayout(processing_button_layout)
        
        self.api_layout = QGridLayout()
        processing_layout.addLayout(self.api_layout)
        
        # Themes
        theme_layout = QVBoxLayout()
        theme_buttons_layout = QHBoxLayout()
        theme_layout.addLayout(theme_buttons_layout)
        
        # Preferences
        preferences_layout = QVBoxLayout()
        preferences_buttons_layout = QHBoxLayout()
        preferences_layout.addLayout(preferences_buttons_layout)
        
        # Sound Effects
        start_sound_layout = QHBoxLayout()
        stop_sound_layout = QHBoxLayout()
        
        # Exports
        export_layout = QHBoxLayout()
        
        self.base_dir = base_dir
        self.local_processing = True

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
        
        speech_label = QLabel("Speech-to-Text")
        self.api_layout.addWidget(speech_label, 1, 0)
        self.speech_dropdown = QComboBox()
        self.api_layout.addWidget(self.speech_dropdown, 1, 1)
        
        summarize_label = QLabel("Summarizer")
        self.api_layout.addWidget(summarize_label, 2, 0)
        self.summarize_dropdown = QComboBox()
        self.api_layout.addWidget(self.summarize_dropdown, 2, 1)

        # Dark, Light, Auto?
        theme_label = QLabel("Application Theme")
        theme_layout.addWidget(theme_label)
        
        self.auto_button = QPushButton("Automatic")
        theme_buttons_layout.addWidget(self.auto_button)
        self.light_button = QPushButton("Light Theme")
        theme_buttons_layout.addWidget(self.light_button)
        self.dark_button = QPushButton("Dark Theme")
        theme_buttons_layout.addWidget(self.dark_button)
        
        # Last used, Set Default, Empty
        preferences_label = QLabel("Recording Preferences")
        preferences_layout.addWidget(preferences_label)
        
        self.last_button = QPushButton("Last Used Options")
        preferences_buttons_layout.addWidget(self.last_button)
        self.default_button = QPushButton("Default Options")
        preferences_buttons_layout.addWidget(self.default_button)
        self.clear_button = QPushButton("Clear Options")
        preferences_buttons_layout.addWidget(self.clear_button)
        
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