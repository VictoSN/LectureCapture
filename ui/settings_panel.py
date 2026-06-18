import shutil

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QSpinBox,
    QFileDialog, QLineEdit, QMessageBox, QScrollArea, QTextEdit, QCheckBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, QSettings, QUrl, Qt, QThread
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtGui import QShortcut, QKeySequence

from core.audio import DEFAULT_SPEECH_MODEL
from models.lecture import Session
from ui.setup_recording import setup_source, setup_audio, update_coord_ranges
from ui.styles import apply_theme, create_button, create_button_label, get_system_theme, no_wheel

from pathlib import Path

class ConnectionTestWorker(QThread):
    """Pings every Gemini model the app might use, off the GUI thread, reporting each
    result as it comes so the user sees which models are available."""
    model_result = pyqtSignal(str, str, str)  # model_id, status, detail
    done = pyqtSignal(bool)                    # any model responded ok

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._key = api_key

    def run(self) -> None:
        from core.gemini import ALL_MODELS, probe_model
        any_ok = False
        for model in ALL_MODELS:
            status, detail = probe_model(self._key, model)
            any_ok = any_ok or status == "ok"
            self.model_result.emit(model, status, detail)
        self.done.emit(any_ok)


class ModelDownloadWorker(QThread):
    """Fetches a faster-whisper model in the background when the user picks it, so the
    first recording isn't blocked on a multi-hundred-MB download. A no-op (and fast) if
    the model is already cached."""
    status = pyqtSignal(str, str)  # model_id, "downloading" | "ready" | "failed"

    def __init__(self, model_id: str) -> None:
        super().__init__()
        self._model_id = model_id

    def run(self) -> None:
        try:
            from faster_whisper import download_model
        except Exception:
            try:
                from faster_whisper.utils import download_model
            except Exception as e:
                print(f"[Model] download unavailable: {e}")
                self.status.emit(self._model_id, "failed")
                return
        # Already cached? local_files_only resolves from disk without touching the network.
        try:
            download_model(self._model_id, local_files_only=True)
            self.status.emit(self._model_id, "ready")
            return
        except Exception:
            pass
        self.status.emit(self._model_id, "downloading")
        try:
            download_model(self._model_id)
            self.status.emit(self._model_id, "ready")
        except Exception as e:
            print(f"[Model] download failed for {self._model_id}: {e}")
            self.status.emit(self._model_id, "failed")


class SettingsPanel(QWidget):
    api_keys_changed = pyqtSignal(str)  # gemini_api_key
    processing_mode_changed = pyqtSignal(str)  # local, api
    theme_changed = pyqtSignal(str)
    sound_effects_changed = pyqtSignal(str, str)  # start path, stop path
    export_clicked = pyqtSignal(int) # session_id
    import_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()
    
    def __init__(self, sessions, base_dir, bundled_sounds_dir, icons_dir, themes_dir) -> None:
        super().__init__()
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setMinimumWidth(400)
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(24, 22, 24, 22)
        main_layout.setSpacing(20)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        self.setLayout(outer_layout)
        
        # Section spacing: a section is a heading label stacked over its controls,
        # with the control rows/grids sharing one consistent gap.
        def _section(v: QVBoxLayout) -> QVBoxLayout:
            v.setSpacing(10)
            return v

        def _row(h: QHBoxLayout) -> QHBoxLayout:
            h.setSpacing(12)
            return h

        def _grid(g: QGridLayout) -> QGridLayout:
            g.setHorizontalSpacing(14)
            g.setVerticalSpacing(10)
            return g

        # Processing
        processing_layout = _section(QVBoxLayout())
        processing_button_layout = _row(QHBoxLayout())
        self.api_layout = _grid(QGridLayout())

        # Themes
        theme_layout = _section(QVBoxLayout())
        theme_buttons_layout = _row(QHBoxLayout())

        # Preferences
        preferences_layout = _section(QVBoxLayout())
        preferences_buttons_layout = _row(QHBoxLayout())
        self.default_layout = _grid(QGridLayout())

        # Sound Effects
        sound_grid_layout = _grid(QGridLayout())

        # Exports & Import
        export_layout = _row(QHBoxLayout())
        import_layout = _row(QHBoxLayout())

        delete_layout = _row(QHBoxLayout())
        action_layout = _row(QHBoxLayout())

        self.settings = QSettings("LectureCapture", "LectureCapture")
        self.base_dir = base_dir
        self.bundled_sounds_dir = bundled_sounds_dir
        self.themes_dir = themes_dir
        self.icons_dir = icons_dir

        # Header Layout
        self.settings_name = QLabel("Settings")
        self.settings_name.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(self.settings_name)

        # API vs Local
        processing_label = QLabel("Processing")
        processing_label.setObjectName("sectionHeader")
        processing_layout.addWidget(processing_label)
        
        self.local_button = create_button_label(icons_dir / "local.svg", "Local", lambda: self.set_proc_mode("local"))
        processing_button_layout.addWidget(self.local_button)

        self.api_button = create_button_label(icons_dir / "server.svg", "API", lambda: self.set_proc_mode("api"))
        processing_button_layout.addWidget(self.api_button)
        processing_layout.addLayout(processing_button_layout)

        processing_note = QLabel("How recordings are transcribed and summarised. Local runs "
                                 "everything on this device (private, no internet needed). API "
                                 "sends the steps you choose to Google Gemini for higher accuracy. "
                                 "Translate / Define always use the Gemini key.")
        processing_note.setWordWrap(True)
        processing_note.setObjectName("muted")
        processing_layout.addWidget(processing_note)

        # Local speech model + Gemini key share ONE grid so their label/control columns
        # line up exactly. Each is: label + control on row 0/6, an explanatory note, then
        # a full-width action button and an on-demand output area. A spacer row separates
        # the two halves.
        local_model_label = QLabel("Local Speech Model")
        self.api_layout.addWidget(local_model_label, 0, 0)

        self.speech_model_dropdown = QComboBox()
        self.speech_model_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        no_wheel(self.speech_model_dropdown)
        for label, value in [
            ("tiny.en — fastest, lowest accuracy", "tiny.en"),
            ("base.en — fast", "base.en"),
            ("small.en — balanced", "small.en"),
            ("distil-small.en — fast, distilled", "distil-small.en"),
            ("medium.en — accurate", "medium.en"),
            ("distil-large-v3 — accurate + fast", "distil-large-v3"),
            ("large-v3 — most accurate", "large-v3"),
        ]:
            self.speech_model_dropdown.addItem(label, value)
        self.speech_model_dropdown.setToolTip(
            "Whisper model used for local speech-to-text. Larger models are more "
            "accurate but heavier; on this machine the GPU runs even large models "
            "far faster than real time."
        )
        # Picking a model downloads it now (activated = user choice only, not the
        # programmatic setCurrentIndex in load_settings / Apply Recommended).
        self.speech_model_dropdown.activated.connect(self._on_speech_model_chosen)
        self._dl_workers = set()
        self.api_layout.addWidget(self.speech_model_dropdown, 0, 1)

        # Note + a download-status line stacked together (the grid row is otherwise full).
        note_box = QWidget()
        note_layout = QVBoxLayout(note_box)
        note_layout.setContentsMargins(0, 0, 0, 0)
        note_layout.setSpacing(4)
        speech_note = QLabel("The on-device Whisper model that turns recorded audio into text. "
                             "Bigger models are more accurate but slower; smaller ones stay "
                             "real-time on modest hardware. Picking a model downloads it once "
                             "(needs internet); Detect Hardware recommends the best fit for this PC.")
        speech_note.setWordWrap(True)
        speech_note.setObjectName("muted")
        note_layout.addWidget(speech_note)
        self.speech_model_status = QLabel("")
        self.speech_model_status.setWordWrap(True)
        self.speech_model_status.setObjectName("muted")
        self.speech_model_status.setVisible(False)
        note_layout.addWidget(self.speech_model_status)
        self.api_layout.addWidget(note_box, 1, 0, 1, 2)

        # Hardware detection — verify the GPU/CPU actually works and recommend a model.
        self._recommended_model = None
        self._hw_worker = None
        self._conn_worker = None
        self._conn_results = {}  # model_id -> (status, detail)

        self.detect_hw_button = QPushButton("Detect Hardware")
        self.detect_hw_button.setToolTip("Check GPU/CPU and recommend a speech model")
        self.detect_hw_button.clicked.connect(self._detect_hardware)
        self.api_layout.addWidget(self.detect_hw_button, 2, 0, 1, 2)

        self.apply_model_button = QPushButton("Apply Recommended")
        self.apply_model_button.setToolTip("Set the recommended model in the dropdown above")
        self.apply_model_button.clicked.connect(self._apply_recommended_model)
        self.apply_model_button.setVisible(False)
        self.api_layout.addWidget(self.apply_model_button, 3, 0, 1, 2)

        self.hw_output = QTextEdit()
        self.hw_output.setReadOnly(True)
        self.hw_output.setMaximumHeight(120)  # ~5 lines; scrolls if longer
        self.hw_output.setPlaceholderText("Hardware details will appear here...")
        self.hw_output.setVisible(False)
        self.api_layout.addWidget(self.hw_output, 4, 0, 1, 2)

        self.api_layout.setRowMinimumHeight(5, 16)  # gap between the local & Gemini halves

        gemini_label = QLabel("Google Gemini API Key")
        self.api_layout.addWidget(gemini_label, 6, 0)
        self.gemini_input = QLineEdit()
        self.gemini_input.setPlaceholderText("AIza...")
        self.gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_layout.addWidget(self.gemini_input, 6, 1)

        api_note = QLabel("Get a free key at aistudio.google.com. Required for Translate / Define, "
                          "and for any steps you run through Gemini in API mode.")
        api_note.setWordWrap(True)
        api_note.setObjectName("muted")
        self.api_layout.addWidget(api_note, 7, 0, 1, 2)

        # Per-engine API selection: each step can independently use the API or the
        # local engine. Only relevant in API mode, so this block hides for Local — but
        # the key + Test above stay visible because Translate / Define always need them.
        self.api_engines_container = QWidget()
        engines_layout = QVBoxLayout(self.api_engines_container)
        engines_layout.setContentsMargins(0, 0, 0, 0)
        engines_layout.setSpacing(8)

        use_label = QLabel("Use API for:")
        engines_layout.addWidget(use_label)

        self.api_use_ocr = QCheckBox("OCR (slides)")
        self.api_use_ocr.setToolTip("Use Gemini vision for slide OCR (captures math/symbols). Off = local Tesseract.")
        self.api_use_speech = QCheckBox("Audio (speech)")
        self.api_use_speech.setToolTip("Use Gemini for speech-to-text. Off = local faster-whisper (recommended for live transcription).")
        self.api_use_summarize = QCheckBox("Summary")
        self.api_use_summarize.setToolTip("Use Gemini to write the session summary. Off = local sumy.")

        use_row = QHBoxLayout()
        use_row.setSpacing(16)
        use_row.addWidget(self.api_use_ocr)
        use_row.addWidget(self.api_use_speech)
        use_row.addWidget(self.api_use_summarize)
        use_row.addStretch()
        use_row_widget = QWidget()
        use_row_widget.setLayout(use_row)
        engines_layout.addWidget(use_row_widget)

        self.api_layout.addWidget(self.api_engines_container, 8, 0, 1, 2)

        self.test_api_button = QPushButton("Test API Connection")
        self.test_api_button.setToolTip("Test the Gemini API key")
        self.test_api_button.clicked.connect(self._test_api_connection)
        self.api_layout.addWidget(self.test_api_button, 9, 0, 1, 2)

        self.api_test_output = QTextEdit()
        self.api_test_output.setReadOnly(True)
        self.api_test_output.setMaximumHeight(100)  # ~5-6 lines; scrolls if longer
        self.api_test_output.setPlaceholderText("Test results will appear here...")
        self.api_test_output.setVisible(False)
        self.api_layout.addWidget(self.api_test_output, 10, 0, 1, 2)

        # Static footnote explaining the results — shown only once a test has run.
        self.api_test_note = QLabel(
            "This is a live check (each line = one request). “Busy” is a temporary 503 on "
            "Google's side, not your quota. “limit N/day” is the published free-tier cap — "
            "the API doesn't report how many you have left, and the AI Studio usage "
            "dashboard lags a little behind real requests."
        )
        self.api_test_note.setObjectName("muted")
        self.api_test_note.setWordWrap(True)
        self.api_test_note.setVisible(False)
        self.api_layout.addWidget(self.api_test_note, 11, 0, 1, 2)

        self.api_layout.setColumnStretch(1, 1)  # control column fills the row width

        self.api_container = QWidget()
        self.api_container.setLayout(self.api_layout)
        processing_layout.addWidget(self.api_container)

        # Dark, Light, Auto?
        theme_label = QLabel("Appearance")
        theme_label.setObjectName("sectionHeader")
        theme_layout.addWidget(theme_label)
        
        theme = get_system_theme()
        self.auto_button = create_button_label(icons_dir / f"{theme}_mode.svg", "Automatic", lambda: self.set_theme("auto"))
        theme_buttons_layout.addWidget(self.auto_button)
        
        self.light_button = create_button_label(icons_dir / "light_mode.svg", "Light Theme", lambda: self.set_theme("light"))
        theme_buttons_layout.addWidget(self.light_button)

        self.dark_button = create_button_label(icons_dir / "dark_mode.svg", "Dark Theme", lambda: self.set_theme("dark"))
        theme_buttons_layout.addWidget(self.dark_button)
        theme_layout.addLayout(theme_buttons_layout)
        
        # Last used, Set Default, Empty
        preferences_label = QLabel("Recording")
        preferences_label.setObjectName("sectionHeader")
        preferences_layout.addWidget(preferences_label)

        self.last_button = create_button_label(icons_dir / "history.svg", "Last Used", lambda: self.set_pref_mode("last"))
        preferences_buttons_layout.addWidget(self.last_button)

        self.default_button = create_button_label(icons_dir / "sliders.svg", "Default", lambda: self.set_pref_mode("default"))
        preferences_buttons_layout.addWidget(self.default_button)

        self.clear_button = create_button_label(icons_dir / "clear.svg", "Empty", lambda: self.set_pref_mode("empty"))
        preferences_buttons_layout.addWidget(self.clear_button)
        preferences_layout.addLayout(preferences_buttons_layout)

        preferences_note = QLabel("What the recording panel is pre-filled with each time you start: "
                                  "Last Used reuses your previous settings, Default applies the "
                                  "values set below, and Empty starts blank.")
        preferences_note.setWordWrap(True)
        preferences_note.setObjectName("muted")
        preferences_layout.addWidget(preferences_note)

        ## Interval
        self.interval_label = QLabel("Default Interval:")
        self.default_layout.addWidget(self.interval_label, 0, 0)

        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 30)
        self.default_layout.addWidget(self.interval_input, 0, 1)

        ## Control Dropdown
        self.capture_method_label = QLabel("Default Capture Method:")
        self.default_layout.addWidget(self.capture_method_label, 1, 0)

        self.capture_method_dropdown = QComboBox()
        no_wheel(self.capture_method_dropdown)
        self.capture_method_dropdown.addItems(["Mouse Select", "Coordinates", "Full Window"])
        self.capture_method_dropdown.currentTextChanged.connect(self.update_ui)
        self.default_layout.addWidget(self.capture_method_dropdown, 1, 1)

        ## Source Dropdown
        self.source_label = QLabel("Default Source:")
        self.default_layout.addWidget(self.source_label, 2, 0)

        self.source_dropdown = QComboBox()
        no_wheel(self.source_dropdown)
        setup_source(self.source_dropdown, icons_dir)
        self.default_layout.addWidget(self.source_dropdown, 2, 1)

        ## Coords Layout
        self.x_label = QLabel("Default X Coordinate:")
        self.default_layout.addWidget(self.x_label, 3, 0)

        self.x_coords = QSpinBox()
        self.default_layout.addWidget(self.x_coords, 3, 1)

        self.y_label = QLabel("Default Y Coordinate:")
        self.default_layout.addWidget(self.y_label, 4, 0)

        self.y_coords = QSpinBox()
        self.default_layout.addWidget(self.y_coords, 4, 1)

        self.width_label = QLabel("Default Width:")
        self.default_layout.addWidget(self.width_label, 5, 0)

        self.width_dimension = QSpinBox()
        self.default_layout.addWidget(self.width_dimension, 5, 1)

        self.height_label = QLabel("Default Height:")
        self.default_layout.addWidget(self.height_label, 6, 0)

        self.height_dimension = QSpinBox()
        self.default_layout.addWidget(self.height_dimension, 6, 1)

        ## Audio
        self.audio_label = QLabel("Default Audio:")
        self.default_layout.addWidget(self.audio_label, 7, 0)

        self.audio_dropdown = QComboBox()
        no_wheel(self.audio_dropdown)
        setup_audio(self.audio_dropdown, icons_dir)
        self.default_layout.addWidget(self.audio_dropdown, 7, 1)

        self.source_dropdown.currentIndexChanged.connect(self._on_source_changed)
        self._on_source_changed()

        self.default_container = QWidget()
        self.default_container.setLayout(self.default_layout)
        preferences_layout.addWidget(self.default_container)
        
        # Start & Stop sound effects
        start_sound_label = QLabel("Start Recording Sound")
        sound_grid_layout.addWidget(start_sound_label, 0, 0)
        
        self.start_sound_dropdown = QComboBox()
        no_wheel(self.start_sound_dropdown)
        sound_grid_layout.addWidget(self.start_sound_dropdown, 0, 1)
        
        self.start_sound_button = create_button(icons_dir / "play.svg", lambda: self.play_sound(self.start_sound_dropdown), width=90)
        self.start_sound_button.setToolTip("Preview start sound")
        sound_grid_layout.addWidget(self.start_sound_button, 0, 2)

        stop_sound_label = QLabel("Stop Recording Sound")
        sound_grid_layout.addWidget(stop_sound_label, 1, 0)

        self.stop_sound_dropdown = QComboBox()
        no_wheel(self.stop_sound_dropdown)
        sound_grid_layout.addWidget(self.stop_sound_dropdown, 1, 1)

        self.stop_sound_button = create_button(icons_dir / "play.svg", lambda: self.play_sound(self.stop_sound_dropdown), width=90)
        self.stop_sound_button.setToolTip("Preview stop sound")
        sound_grid_layout.addWidget(self.stop_sound_button, 1, 2)

        sound_import_label = QLabel("Import Sound")
        sound_grid_layout.addWidget(sound_import_label, 2, 0)

        sound_import_button = create_button(icons_dir / "import.svg", self.import_sound, width=90)
        sound_import_button.setToolTip("Import a custom sound file")
        sound_grid_layout.addWidget(sound_import_button, 2, 2)
        
        # Export & Import Sessions
        export_label = QLabel("Export Session")
        export_layout.addWidget(export_label)
        
        self.export_dropdown = QComboBox()
        no_wheel(self.export_dropdown)
        export_layout.addWidget(self.export_dropdown)
        
        self.export_button = create_button(icons_dir / "export.svg", lambda: self.export_clicked.emit(self.export_dropdown.currentData()), width=90)
        self.export_button.setToolTip("Export selected session")
        export_layout.addWidget(self.export_button)

        import_label = QLabel("Import Session")
        import_layout.addWidget(import_label)

        self.import_button = create_button(icons_dir / "import.svg", self.import_clicked.emit, width=90)
        self.import_button.setToolTip("Import a session file")
        import_layout.addWidget(self.import_button)

        delete_label = QLabel("Delete all sessions. This cannot be undone.")
        delete_label.setObjectName("muted")
        delete_layout.addWidget(delete_label)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Permanently delete all sessions")
        self.delete_button.clicked.connect(self.deleteEvent)
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #b54b35;
                color: #ffffff;
                border: none;
                padding: 7px 14px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #9c3f2c;
            }
        """)
        delete_layout.addWidget(self.delete_button)
        
        # Close & Save Buttons
        self.cancel_button = QPushButton("Close")
        self.cancel_button.setToolTip("Close settings (Esc)")
        self.cancel_button.clicked.connect(self._on_cancel)
        action_layout.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        self.save_button.setToolTip("Save settings (Return)")
        action_layout.addWidget(self.save_button)
        self.save_button.clicked.connect(self._on_save)
        action_layout.insertStretch(0)

        # Assemble sections, each separated by a divider so they read as distinct
        # groups. The Processing / Appearance / Recording layouts carry their own
        # section headers; the rest get one here.
        main_layout.addLayout(processing_layout)
        main_layout.addWidget(self._divider())
        main_layout.addLayout(theme_layout)
        main_layout.addWidget(self._divider())
        main_layout.addLayout(preferences_layout)
        main_layout.addWidget(self._divider())
        main_layout.addWidget(self._section_header("Sound Effects"))
        main_layout.addLayout(sound_grid_layout)
        main_layout.addWidget(self._divider())
        main_layout.addWidget(self._section_header("Sessions"))
        main_layout.addLayout(export_layout)
        main_layout.addLayout(import_layout)
        main_layout.addWidget(self._divider())
        main_layout.addWidget(self._section_header("Danger Zone", danger=True))
        main_layout.addLayout(delete_layout)
        main_layout.addStretch()
        main_layout.addLayout(action_layout)

        self.setup_sound_effects() # Populate dropdowns first
        self.load_settings() # Set values for the dropdown
        self.refresh_sessions(sessions)
        self.update_ui()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_save)

    def _section_header(self, text: str, danger: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dangerHeader" if danger else "sectionHeader")
        return label

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("sectionDivider")
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    def _set_selected(self, btn, selected: bool) -> None:
        # Toggle the [selected] property the QSS keys off, then repolish so the new
        # style applies immediately (Qt doesn't re-evaluate property selectors on its own).
        btn.setProperty("selected", selected)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _refresh_active_buttons(self) -> None:
        # Highlight the active choice in each toggle group. getattr guards calls that
        # happen mid-construction before every mode attribute is set.
        for mapping, active in (
            ({"local": self.local_button, "api": self.api_button}, getattr(self, "proc_mode", None)),
            ({"auto": self.auto_button, "light": self.light_button, "dark": self.dark_button}, getattr(self, "theme", None)),
            ({"last": self.last_button, "default": self.default_button, "empty": self.clear_button}, getattr(self, "pref_mode", None)),
        ):
            for key, btn in mapping.items():
                self._set_selected(btn, key == active)

    def update_ui(self) -> None:
        # Processing Visibility. The key + Test Connection stay visible in both modes
        # (Translate / Define always need them); only the per-engine pipeline toggles
        # are specific to API mode.
        self.api_engines_container.setVisible(self.proc_mode == "api")
        self.default_container.setVisible(self.pref_mode == "default")
        self._refresh_active_buttons()

        # Coordinates Visibility
        method = self.capture_method_dropdown.currentText()
        is_coords = method == "Coordinates"

        self.x_label.setVisible(is_coords)
        self.x_coords.setVisible(is_coords)
        self.y_label.setVisible(is_coords)
        self.y_coords.setVisible(is_coords)
        self.width_label.setVisible(is_coords)
        self.width_dimension.setVisible(is_coords)
        self.height_label.setVisible(is_coords)
        self.height_dimension.setVisible(is_coords)
            
    def set_proc_mode(self, mode):
        self.proc_mode = mode
        self.settings.setValue("processing_mode", mode)
        self.settings.sync()
        self.update_ui()
        self.processing_mode_changed.emit(mode)
        
    def set_pref_mode(self, mode):
        self.pref_mode = mode
        self.update_ui()

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
    
    def setup_sound_effects(self) -> None:
        sound_dir = Path(self.base_dir) / 'sound_effects'
        self.start_sound_dropdown.addItem("None", None)
        self.stop_sound_dropdown.addItem("None", None)
        
        seen = set()
        for wav in list(self.bundled_sounds_dir.glob("*.wav")) + list(sound_dir.glob("*.wav")):
            if wav.name not in seen:
                seen.add(wav.name)
                self.start_sound_dropdown.addItem(wav.name, str(wav))
                self.stop_sound_dropdown.addItem(wav.name, str(wav))
        
        saved_start = self.settings.value("start_sound", str(self.bundled_sounds_dir / 'Beep 1 (Default).wav'))
        saved_stop = self.settings.value("stop_sound", str(self.bundled_sounds_dir / 'Chirp 1 (Default).wav'))

        for saved, dropdown in [(saved_start, self.start_sound_dropdown), (saved_stop, self.stop_sound_dropdown)]:
            if saved:
                idx = dropdown.findData(saved)
                if idx >= 0:
                    dropdown.setCurrentIndex(idx)
    
    def play_sound(self, dropdown: QComboBox) -> None:
        path = dropdown.currentData()
        if path:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(path))
            effect.play()
            self._preview_sound = effect
    
    def _on_save(self) -> None:
        # Save preferences mode
        self.settings.setValue("preferences_mode", self.pref_mode)
        
        # Save theme
        self.settings.setValue("theme", self.theme)

        # Save Recording Preferences        
        self.settings.setValue("default_interval", self.interval_input.value())
        self.settings.setValue("default_capture_method", self.capture_method_dropdown.currentText())
        self.settings.setValue("default_source", self.source_dropdown.currentText())
        self.settings.setValue("default_region", {
            "left": self.x_coords.value(),
            "top": self.y_coords.value(),
            "width": self.width_dimension.value(),
            "height": self.height_dimension.value()
        })
        self.settings.setValue("default_audio", self.audio_dropdown.currentText())
        
        # Ensure that its saved
        self.settings.sync()
        
        # Save Sound Effects
        start = self.start_sound_dropdown.currentData() or ""
        stop = self.stop_sound_dropdown.currentData() or ""
        self.sound_effects_changed.emit(start, stop)

        # Save API key + per-engine API selection
        gemini_key = self.gemini_input.text().strip()
        self.settings.setValue("api_key_gemini", gemini_key)
        self.settings.setValue("api_use_ocr", self.api_use_ocr.isChecked())
        self.settings.setValue("api_use_speech", self.api_use_speech.isChecked())
        self.settings.setValue("api_use_summarize", self.api_use_summarize.isChecked())
        self.settings.setValue("speech_model", self.speech_model_dropdown.currentData())
        self.settings.sync()
        self.api_keys_changed.emit(gemini_key)
        self.processing_mode_changed.emit(self.proc_mode)
    
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
    
    def reload_sources(self) -> None:
        # Re-enumerate monitors/windows and audio devices so the dropdowns reflect
        # what's open right now (called each time the panel is shown).
        setup_source(self.source_dropdown, self.icons_dir)
        setup_audio(self.audio_dropdown, self.icons_dir)

    def load_settings(self) -> None:
        self.proc_mode = str(self.settings.value("processing_mode", "local")) # local, api
        self.revert_theme() # theme
        self.pref_mode = str(self.settings.value("preferences_mode", "last")) # last, default, empty
        
        region = self.settings.value("default_region", {"left": 0, "top": 0, "width": 800, "height": 800})
    
        self.interval_input.setValue(int(self.settings.value("default_interval", 10)))
        self.capture_method_dropdown.setCurrentText(self.settings.value("default_capture_method", "Mouse Select"))
        idx = self.source_dropdown.findText(self.settings.value("default_source", ""))
        if idx >= 0:
            self.source_dropdown.setCurrentIndex(idx)
        self.x_coords.setValue(int(region["left"]))
        self.y_coords.setValue(int(region["top"]))
        self.width_dimension.setValue(int(region["width"]))
        self.height_dimension.setValue(int(region["height"]))
        self.audio_dropdown.setCurrentText(self.settings.value("default_audio", ""))
        
        self._set_dropdown(self.start_sound_dropdown, self.settings.value("start_sound"), str(self.bundled_sounds_dir / 'Beep 1 (Default).wav'))
        self._set_dropdown(self.stop_sound_dropdown, self.settings.value("stop_sound"), str(self.bundled_sounds_dir / 'Chirp 1 (Default).wav'))

        # Load API key + per-engine API selection (default: all on, = old behaviour)
        self.gemini_input.setText(self.settings.value("api_key_gemini", ""))
        self.api_use_ocr.setChecked(self.settings.value("api_use_ocr", True, type=bool))
        self.api_use_speech.setChecked(self.settings.value("api_use_speech", True, type=bool))
        self.api_use_summarize.setChecked(self.settings.value("api_use_summarize", True, type=bool))
        sm_idx = self.speech_model_dropdown.findData(self.settings.value("speech_model", DEFAULT_SPEECH_MODEL))
        if sm_idx < 0:  # unknown/legacy value (e.g. the retired "auto") → fall back to default
            sm_idx = self.speech_model_dropdown.findData(DEFAULT_SPEECH_MODEL)
        if sm_idx >= 0:
            self.speech_model_dropdown.setCurrentIndex(sm_idx)
        
    def revert_theme(self) -> None:
        self.set_theme(str(self.settings.value("theme", "auto")))
    
    def _on_cancel(self) -> None:        
        self.revert_theme()
        self.load_settings()
        self.update_ui()
        self.cancel_clicked.emit()
    
    def set_theme(self, theme: str) -> None:
        self.theme = theme
        apply_theme(theme, self.themes_dir)
        self._refresh_active_buttons()
        self.theme_changed.emit(theme)

    def _set_dropdown(self, dropdown: QComboBox, path: str, default: str) -> None:
        resolved = path if path and Path(path).exists() else default
        idx = dropdown.findData(resolved)
        if idx >= 0:
            dropdown.setCurrentIndex(idx)
    
    def _test_api_connection(self) -> None:
        key = self.gemini_input.text().strip()
        self.api_test_output.setVisible(True)
        if not key:
            self.api_test_output.setPlainText("No API key entered.")
            return
        if self._conn_worker is not None:
            return  # a test is already running

        from core.gemini import ALL_MODELS
        # List every model upfront as "testing" so the user sees all of them are being
        # checked; each line updates in place as its result lands.
        self._conn_results = {model: ("testing", "") for model in ALL_MODELS}
        self.api_test_note.setVisible(True)  # mirror the output box's visibility
        self.test_api_button.setDisabled(True)
        self._render_conn_results()
        self._conn_worker = ConnectionTestWorker(key)
        self._conn_worker.model_result.connect(self._on_model_tested)
        self._conn_worker.done.connect(self._on_conn_test_done)
        self._conn_worker.finished.connect(self._on_conn_test_finished)
        self._conn_worker.start()

    def _render_conn_results(self, extra: str = "") -> None:
        from core.gemini import pretty_model, FREE_TIER_RPD
        # icon, label per status. "busy" (503) is transient, not a failure.
        info = {
            "testing":     ("•", "testing…"),
            "ok":          ("✓", "available"),
            "busy":        ("⏳", "temporarily busy (try again)"),
            "limited":     ("✗", "daily limit reached"),
            "missing":     ("✗", "not available"),
            "invalid_key": ("✗", "invalid API key"),
            "error":       ("✗", "error"),
        }
        lines = []
        for model, (status, detail) in self._conn_results.items():
            icon, label = info.get(status, ("✗", status))
            rpd = FREE_TIER_RPD.get(model)
            rpd_txt = f"  ·  limit {rpd}/day" if rpd else ""
            line = f"{icon}  {pretty_model(model)} — {label}{rpd_txt}"
            # Only surface the raw error text for genuinely unexpected failures.
            if status in ("error", "invalid_key") and detail:
                line += f"\n      {detail}"
            lines.append(line)
        self.api_test_output.setPlainText("\n".join(lines) + extra)

    def _on_model_tested(self, model: str, status: str, detail: str) -> None:
        self._conn_results[model] = (status, detail)
        self._render_conn_results()

    def _on_conn_test_done(self, any_ok: bool) -> None:
        statuses = {status for status, _ in self._conn_results.values()}
        if any_ok or "busy" in statuses:
            extra = ""  # the key and connection work; usable now or after a brief retry
        elif "invalid_key" in statuses:
            extra = "\n\nThe API key looks invalid — double-check it in the field above."
        elif "limited" in statuses:
            extra = "\n\nEvery available model has hit today's free-tier limit — try again tomorrow."
        else:
            extra = "\n\nNo models responded — check the key and your connection."
        self._render_conn_results(extra)

    def _on_conn_test_finished(self) -> None:
        self.test_api_button.setDisabled(False)
        self._conn_worker = None

    def _detect_hardware(self) -> None:
        from core.hardware import HardwareProbeWorker
        if self._hw_worker is not None:
            return  # a probe is already running
        self.detect_hw_button.setDisabled(True)
        self.apply_model_button.setVisible(False)
        self.hw_output.setVisible(True)
        self.hw_output.setPlainText("Detecting hardware… (this can take a few seconds)")
        self._hw_worker = HardwareProbeWorker()
        self._hw_worker.done.connect(self._on_hardware_detected)
        self._hw_worker.failed.connect(self._on_hardware_failed)
        self._hw_worker.finished.connect(self._on_hardware_finished)
        self._hw_worker.start()

    def _on_hardware_detected(self, report: str, recommended: str) -> None:
        self.hw_output.setPlainText(report)
        self._recommended_model = recommended
        # Offer Apply only if the recommendation isn't already selected.
        already = self.speech_model_dropdown.currentData() == recommended
        self.apply_model_button.setVisible(bool(recommended) and not already)

    def _on_hardware_failed(self, message: str) -> None:
        self.hw_output.setPlainText(f"Hardware detection failed:\n{message}")

    def _on_hardware_finished(self) -> None:
        self.detect_hw_button.setDisabled(False)
        self._hw_worker = None

    def _apply_recommended_model(self) -> None:
        if not self._recommended_model:
            return
        idx = self.speech_model_dropdown.findData(self._recommended_model)
        if idx >= 0:
            self.speech_model_dropdown.setCurrentIndex(idx)
        self.apply_model_button.setVisible(False)
        self._download_speech_model(self._recommended_model)

    def _on_speech_model_chosen(self, index: int) -> None:
        # Fired only on a user selection (not programmatic) — fetch it now.
        self._download_speech_model(self.speech_model_dropdown.itemData(index))

    def _download_speech_model(self, model_id: str) -> None:
        if not model_id:
            return
        worker = ModelDownloadWorker(model_id)
        worker.status.connect(self._on_model_download_status)
        worker.finished.connect(lambda w=worker: self._dl_workers.discard(w))
        self._dl_workers.add(worker)
        worker.start()

    def _on_model_download_status(self, model: str, state: str) -> None:
        if state == "downloading":
            text = f"Downloading {model}… one-time, needs internet (this can take a while)."
        elif state == "ready":
            text = f"{model} is downloaded and ready for offline use."
        else:
            text = f"Couldn't download {model} — check your internet connection."
        self.speech_model_status.setText(text)
        self.speech_model_status.setVisible(True)

    def deleteEvent(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete All Session",
            "Delete all of the sessions?"
        )
        if reply == QMessageBox.StandardButton.No:
            return
        else:
            self.delete_clicked.emit()