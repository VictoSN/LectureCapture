import shutil

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QSpinBox, QFileDialog, QLineEdit
)
from PyQt6.QtCore import pyqtSignal, QSettings, QUrl
from PyQt6.QtMultimedia import QSoundEffect

from models.lecture import Session
from ui.set_layout_visible import set_layout_visible
from ui.setup_recording import setup_monitor, setup_audio

from pathlib import Path

class SettingsPanel(QWidget):
    sound_effects_changed = pyqtSignal(str, str)  # start path, stop path
    export_clicked = pyqtSignal(int) # session_id
    import_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()
    
    def __init__(self, sessions, base_dir) -> None:
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
        sound_layout = QVBoxLayout()
        sound_grid_layout = QGridLayout()
        
        # Exports & Import
        export_layout = QHBoxLayout()
        import_layout = QHBoxLayout()

        action_layout = QHBoxLayout()

        self.settings = QSettings("LectureCapture", "LectureCapture")
        self.base_dir = base_dir
        self.proc_mode = str(self.settings.value("processing_mode", "local")) # local, api
        self.pref_mode = str(self.settings.value("preferences_mode", "last")) # last, default, empty

        # Header Layout
        self.settings_name = QLabel("Settings")
        main_layout.addWidget(self.settings_name)

        # API vs Local
        processing_label = QLabel("Processing Location")
        processing_layout.addWidget(processing_label)
        
        self.local_button = QPushButton("Local")
        processing_button_layout.addWidget(self.local_button)
        self.local_button.clicked.connect(lambda: self.set_proc_mode("local"))
        
        self.api_button = QPushButton("API")
        processing_button_layout.addWidget(self.api_button)
        self.api_button.clicked.connect(lambda: self.set_proc_mode("api"))
        processing_layout.addLayout(processing_button_layout)
        
        ocr_label = QLabel("OCR")
        self.api_layout.addWidget(ocr_label, 0, 0)
        self.ocr_input = QLineEdit()
        self.api_layout.addWidget(self.ocr_input, 0, 1)
        
        speech_label = QLabel("Speech-to-Text")
        self.api_layout.addWidget(speech_label, 1, 0)
        self.speech_input = QLineEdit()
        self.api_layout.addWidget(self.speech_input, 1, 1)
        
        summarize_label = QLabel("Summarizer")
        self.api_layout.addWidget(summarize_label, 2, 0)
        self.summarize_input = QLineEdit()
        self.api_layout.addWidget(self.summarize_input, 2, 1)

        self.api_container = QWidget()
        self.api_container.setLayout(self.api_layout)
        processing_layout.addWidget(self.api_container)

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
        self.last_button.clicked.connect(lambda: self.set_pref_mode("last"))
        preferences_buttons_layout.addWidget(self.last_button)

        self.default_button = QPushButton("Default Options")
        self.default_button.clicked.connect(lambda: self.set_pref_mode("default"))
        preferences_buttons_layout.addWidget(self.default_button)

        self.clear_button = QPushButton("Empty Options")
        self.clear_button.clicked.connect(lambda: self.set_pref_mode("empty"))
        preferences_buttons_layout.addWidget(self.clear_button)
        preferences_layout.addLayout(preferences_buttons_layout)

        ## Interval
        self.interval_label = QLabel("Default Interval")
        self.default_layout.addWidget(self.interval_label, 0, 0)
        
        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 30)
        self.default_layout.addWidget(self.interval_input, 0, 1)
        
        ## Control Dropdown
        self.capture_method_label = QLabel("Default Capture Method")
        self.default_layout.addWidget(self.capture_method_label, 1, 0)
        
        self.capture_method_dropdown = QComboBox()
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.default_layout.addWidget(self.capture_method_dropdown, 1, 1)

        ## Monitor Dropdown
        self.monitor_label = QLabel("Default Monitor")
        self.default_layout.addWidget(self.monitor_label, 2, 0)

        self.monitor_dropdown = QComboBox()
        setup_monitor(self.monitor_dropdown)
        self.default_layout.addWidget(self.monitor_dropdown, 2, 1)

        ## Coords Layout
        self.x_label = QLabel("Default X Coordinate")
        self.default_layout.addWidget(self.x_label, 3, 0)

        self.x_coords = QSpinBox()
        self.x_coords.setRange(0, 5000)
        self.default_layout.addWidget(self.x_coords, 3, 1)

        self.y_label = QLabel("Default Y Coordinate")
        self.default_layout.addWidget(self.y_label, 4, 0)

        self.y_coords = QSpinBox()
        self.y_coords.setRange(0, 5000)
        self.default_layout.addWidget(self.y_coords, 4, 1)

        self.width_label = QLabel("Default Width")
        self.default_layout.addWidget(self.width_label, 5, 0)

        self.width_dimension = QSpinBox()
        self.width_dimension.setRange(0, 5000)
        self.default_layout.addWidget(self.width_dimension, 5, 1)

        self.height_label = QLabel("Default Height")
        self.default_layout.addWidget(self.height_label, 6, 0)

        self.height_dimension = QSpinBox()
        self.height_dimension.setRange(0, 5000)
        self.default_layout.addWidget(self.height_dimension, 6, 1)

        self.default_container = QWidget()
        self.default_container.setLayout(self.default_layout)
        preferences_layout.addWidget(self.default_container)

        # Audio
        self.audio_label = QLabel("Default Audio")
        self.default_layout.addWidget(self.audio_label, 7, 0)

        self.audio_dropdown = QComboBox()
        setup_audio(self.audio_dropdown)
        self.default_layout.addWidget(self.audio_dropdown, 7, 1)
        
        # Start & Stop sound effects
        sound_label = QLabel("Sound Effects")
        sound_layout.addWidget(sound_label)
        
        start_sound_label = QLabel("Start Recording Sound Effects")
        sound_grid_layout.addWidget(start_sound_label, 0, 0)
        
        self.start_sound_dropdown = QComboBox()
        sound_grid_layout.addWidget(self.start_sound_dropdown, 0, 1)
        
        self.start_sound_button = QPushButton("Play")
        self.start_sound_button.clicked.connect(lambda: self.play_sound(self.start_sound_dropdown))
        sound_grid_layout.addWidget(self.start_sound_button, 0, 2)

        stop_sound_label = QLabel("Stop Recording Sound Effects")
        sound_grid_layout.addWidget(stop_sound_label, 1, 0)
        
        self.stop_sound_dropdown = QComboBox()
        sound_grid_layout.addWidget(self.stop_sound_dropdown, 1, 1)
        
        self.stop_sound_button = QPushButton("Play")
        self.stop_sound_button.clicked.connect(lambda: self.play_sound(self.stop_sound_dropdown))
        sound_grid_layout.addWidget(self.stop_sound_button, 1, 2)

        sound_import_label = QLabel("Import Sound")
        sound_grid_layout.addWidget(sound_import_label, 2, 0)
        
        sound_import_button = QPushButton("Import")
        sound_import_button.clicked.connect(self.import_sound)
        sound_grid_layout.addWidget(sound_import_button, 2, 2)
        sound_layout.addLayout(sound_grid_layout)
        
        # Export & Import Sessions
        export_label = QLabel("Export Session")
        export_layout.addWidget(export_label)
        self.export_dropdown = QComboBox()
        export_layout.addWidget(self.export_dropdown)
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(lambda: self.export_clicked.emit(self.export_dropdown.currentData()))
        export_layout.addWidget(self.export_button)
        
        import_label = QLabel("Import Session")
        import_layout.addWidget(import_label)
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self.import_clicked)
        import_layout.addWidget(self.import_button)
        
        # Cancel & Save Buttons
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        action_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Save")
        action_layout.addWidget(self.save_button)
        self.save_button.clicked.connect(self._on_save)

        main_layout.addLayout(processing_layout)
        main_layout.addLayout(theme_layout)
        main_layout.addLayout(preferences_layout)
        main_layout.addLayout(sound_layout)
        main_layout.addLayout(export_layout)
        main_layout.addLayout(import_layout)
        main_layout.addLayout(action_layout)
        self.setLayout(main_layout)

        self.setup_sound_effects() # Populate dropdowns first
        self.load_settings() # Set values for the dropdown
        self.refresh_sessions(sessions)
        self.update_ui()

    def update_ui(self):
        self.api_container.setVisible(self.proc_mode == "api")
        self.default_container.setVisible(self.pref_mode == "default")

    def set_proc_mode(self, mode):
        self.proc_mode = mode
        self.settings.setValue("processing_mode", mode)
        self.settings.sync()
        self.update_ui()
        
    def set_pref_mode(self, mode):
        self.pref_mode = mode
        self.settings.setValue("preferences_mode", mode)
        self.settings.sync()
        self.update_ui()

    def setup_sound_effects(self) -> None:
        sound_dir = Path(self.base_dir) / 'sound_effects'
        self.start_sound_dropdown.addItem("None", None)
        self.stop_sound_dropdown.addItem("None", None)
        
        for wav in sound_dir.glob("*.wav"):
            self.start_sound_dropdown.addItem(wav.name, str(wav))
            self.stop_sound_dropdown.addItem(wav.name, str(wav))
        
        saved_start = self.settings.value("start_sound", str(Path(self.base_dir) / 'sound_effects' / 'Beep 1 (Default).wav'))
        saved_stop = self.settings.value("stop_sound", str(Path(self.base_dir) / 'sound_effects' / 'Chirp 1 (Default).wav'))
    
        if saved_start:
            idx = self.start_sound_dropdown.findData(saved_start)
            if idx >= 0:
                self.start_sound_dropdown.setCurrentIndex(idx)
        
        if saved_stop:
            idx = self.stop_sound_dropdown.findData(saved_stop)
            if idx >= 0:
                self.stop_sound_dropdown.setCurrentIndex(idx)
    
    def play_sound(self, dropdown: QComboBox) -> None:
        path = dropdown.currentData()
        if path:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(path))
            effect.play()
            self._preview_sound = effect
    
    def _on_save(self) -> None:
        # Save Recording Preferences        
        self.settings.setValue("default_interval", self.interval_input.value())
        self.settings.setValue("default_capture_method", self.capture_method_dropdown.currentText())
        self.settings.setValue("default_monitor", self.monitor_dropdown.currentText())
        self.settings.setValue("default_region", {
            "left": self.x_coords.value(),
            "top": self.y_coords.value(),
            "width": self.width_dimension.value(),
            "height": self.height_dimension.value()
        })
        self.settings.setValue("default_audio", self.audio_dropdown.currentText())
        
        # Save Sound Effects
        start = self.start_sound_dropdown.currentData() or ""
        stop = self.stop_sound_dropdown.currentData() or ""
        self.sound_effects_changed.emit(start, stop)
    
    def import_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Sound", "", "WAV Files (*.wav)")
        if path:
            dst = Path(self.base_dir) / 'sound_effects' / Path(path).name
            
            # Ensure there is no file with the same name
            if not dst.exists():
                shutil.copy2(path, dst)
                self.start_sound_dropdown.addItem(Path(path).name, str(dst))
                self.stop_sound_dropdown.addItem(Path(path).name, str(dst))
    
    def refresh_sessions(self, sessions: list[Session]) -> None:
        self.export_dropdown.clear()
        for session in sessions:
            self.export_dropdown.addItem(session.name, session.id)
    
    def load_settings(self) -> None:
        region = self.settings.value("default_region", {"left": 0, "top": 0, "width": 800, "height": 800})
    
        self.interval_input.setValue(int(self.settings.value("default_interval", 10)))
        self.capture_method_dropdown.setCurrentText(self.settings.value("default_capture_method", "Mouse Select"))
        self.monitor_dropdown.setCurrentText(self.settings.value("default_monitor", "Monitor 1"))
        self.x_coords.setValue(int(region["left"]))
        self.y_coords.setValue(int(region["top"]))
        self.width_dimension.setValue(int(region["width"]))
        self.height_dimension.setValue(int(region["height"]))
        self.audio_dropdown.setCurrentText(self.settings.value("default_audio", ""))
        
        saved_start = self.settings.value("start_sound", str(Path(self.base_dir) / 'sound_effects' / 'Beep 1 (Default).wav'))
        saved_stop = self.settings.value("stop_sound", str(Path(self.base_dir) / 'sound_effects' / 'Chirp 1 (Default).wav'))
        
        idx = self.start_sound_dropdown.findData(saved_start)
        if idx >= 0:
            self.start_sound_dropdown.setCurrentIndex(idx)
        
        idx = self.stop_sound_dropdown.findData(saved_stop)
        if idx >= 0:
            self.stop_sound_dropdown.setCurrentIndex(idx)

    def _on_cancel(self) -> None:
        self.load_settings()
        self.cancel_clicked.emit()