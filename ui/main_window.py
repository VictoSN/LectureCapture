import time
import zipfile, json

from qframelesswindow import FramelessMainWindow
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QApplication, QInputDialog, QDialog
from ui.grip_splitter import GripSplitter
from PyQt6.QtGui import QShortcut, QKeySequence, QGuiApplication, QCursor, QIcon
from PyQt6.QtCore import Qt, QTimer, QUrl, QSettings
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from pathlib import Path
from datetime import datetime

from models.lecture import Session, OCRCapture
from storage.database import Storage
from core.resources import resource_root
from core.ocr import OCRWorker
from core.audio import AudioWorker, MediaImportWorker, DEFAULT_SPEECH_MODEL
from core.api_errors import SHORT_STATUS
from core.summarizer import SummarizeWorker
from core.quiz import QuizWorker, source_hash
from core.gemini import FREQUENT_MODEL_CHAIN, pretty_model
from ui.format_time import FormatClock
from ui.title_bar import CustomTitleBar
from ui.capture_overlay import CaptureOverlay
from ui.sidebar import Sidebar
from ui.category_picker import merged_activity_categories
from ui.new_session_panel import NewSessionPanel
from ui.transcript_panel import TranscriptPanel
from ui.properties_panel import PropertiesPanel
from ui.recording_panel import RecordingPanel
from ui.settings_panel import SettingsPanel
from ui.quiz_panel import QuizPanel
from ui.help_panel import HelpPanel
from ui.styles import refresh_icons

_ASSETS = resource_root() / 'assets'  # project root from source, bundle dir when frozen
BUNDLED_SOUNDS_DIR = _ASSETS / 'sound_effects'
ICONS_DIR = _ASSETS / 'icons'
THEMES_DIR = _ASSETS / 'themes'

class MainWindow(FramelessMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()
        self.settings = QSettings("LectureCapture", "LectureCapture")
        # Migrate the retired "auto" speech model to a concrete default. Detect Hardware
        if str(self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)) == "auto":
            self.settings.setValue("speech_model", DEFAULT_SPEECH_MODEL)
        self.current_session = None
        self.is_recording = False
        self.is_paused = False
        self.is_new_session_open = False
        self.is_settings_open = False
        self.is_properties_open = False
        self.is_recording_open = False

        # Block stale saves during session load so date_modified doesn't get bumped.
        self._load_guard_until = 0.0

        # Speech that arrived before the first slide was captured.
        self._pending_speech = ""
        self._pending_capture_id = None

        # Translate/define lookups.
        self._lookup_popup = None
        self._lookup_worker = None
        self._lookup_workers = set()

        self._summarize_worker = None
        self._import_worker = None
        self._import_active = False
        self._model_download_active = False

        # Window details
        self.setWindowIcon(QIcon(str(ICONS_DIR / 'logo.ico')))
        self.setWindowTitle("LectureCapture")
        self.setMinimumSize(800, 300)
        self.resize(1300, 800)
        
        # Move it to the middle
        screen = QGuiApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())
        
        # Restore last window geometry/maximized state, if we have one saved.
        self._restore_window_state()
        
        # Default Sound Effects
        self.DEFAULT_START_SOUND = str(BUNDLED_SOUNDS_DIR / 'Beep 1 (Default).wav')
        self.DEFAULT_STOP_SOUND = str(BUNDLED_SOUNDS_DIR / 'Chirp 1 (Default).wav')

        # `or DEFAULT`: empty string means user chose "None", absent key means first launch.
        start_path = self.settings.value("start_sound")
        if not start_path and start_path is not None:
            pass  # user chose "None", keep empty
        elif not start_path:
            start_path = self.DEFAULT_START_SOUND
        stop_path = self.settings.value("stop_sound")
        if not stop_path and stop_path is not None:
            pass  # user chose "None"
        elif not stop_path:
            stop_path = self.DEFAULT_STOP_SOUND
        
        self._start_output = QAudioOutput()
        self.start_audio = QMediaPlayer()
        self.start_audio.setAudioOutput(self._start_output)
        self.start_audio.setSource(QUrl.fromLocalFile(start_path) if start_path else QUrl())

        self._stop_output = QAudioOutput()
        self.stop_audio = QMediaPlayer()
        self.stop_audio.setAudioOutput(self._stop_output)
        self.stop_audio.setSource(QUrl.fromLocalFile(stop_path) if stop_path else QUrl())
        
        self.filter_name = ""
        self.filter_category = ""
        self.filter_module = ""

        # Title Bar
        self.setTitleBar(CustomTitleBar(self, ICONS_DIR))
        self.setContentsMargins(0, self.titleBar.height(), 0, 0)
        self.titleBar.raise_()
        self.titleBar.new_session_button.clicked.connect(self.on_new_session_clicked)
        self.titleBar.settings_button.clicked.connect(self.on_settings_clicked)
        self.titleBar.help_button.clicked.connect(self.on_help_clicked)
        self.titleBar.sidebar_button.clicked.connect(self._toggle_sidebar)
        self._sidebar_width = 260  # last known open width
        self._sidebar_open_before_help = False  # so closing help restores the sidebar

        # Splitter Layout
        self.splitter = GripSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.elapse_s = 0

        sessions = self.storage.get_all_sessions()
        module_categories = self.storage.get_module_categories() # Get all module categories
        self.sidebar = Sidebar(sessions, self.on_session_selected, self._activity_categories(), module_categories, ICONS_DIR)
        self.sidebar.new_session_clicked.connect(self.on_new_session_clicked)
        self.sidebar.settings_clicked.connect(self.on_settings_clicked)
        self.splitter.addWidget(self.sidebar)
        # Keep sidebar width sane to prevent splitter collapse.
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(380)
        # Prevent drag-collapse to 0 (no handle at 0); toggle with setVisible instead.
        self.splitter.setCollapsible(0, False)
        
        self.sidebar.search_changed.connect(self.on_search_changed)
        self.sidebar.category_filter_changed.connect(self.on_category_filter_changed)
        self.sidebar.module_filter_changed.connect(self.on_module_filter_changed)

        # New Session Panel
        self.new_session_panel = NewSessionPanel(self._activity_categories(), self.storage.get_module_categories())
        self.new_session_panel.create_clicked.connect(
            lambda session_name, activity_category, module_category: self.on_new_session_create(session_name, activity_category, module_category)
        )
        self.new_session_panel.cancel_clicked.connect(self.on_new_session_cancelled)
        
        self.splitter.addWidget(self.new_session_panel)
        self.new_session_panel.setVisible(False)
        
        # Init the settings, and hide it
        self.settings_panel = SettingsPanel(sessions, self.storage.base_dir, BUNDLED_SOUNDS_DIR, ICONS_DIR, THEMES_DIR)
        self.settings_panel.api_keys_changed.connect(self.on_api_keys_changed)
        self.settings_panel.processing_mode_changed.connect(self.on_processing_mode_changed)
        self.settings_panel.theme_changed.connect(lambda theme: self._on_theme_changed(theme))
        self.settings_panel.sound_effects_changed.connect(self.on_sound_effects_changed)
        self.settings_panel.export_clicked.connect(self.on_export_clicked)
        self.settings_panel.import_clicked.connect(self.on_import_clicked)
        self.settings_panel.cancel_clicked.connect(self.on_settings_clicked)
        self.settings_panel.delete_clicked.connect(self.on_all_deleted_clicked)
        self.settings_panel.help_requested.connect(self.on_settings_help_requested)
        self.settings_panel.model_download_active.connect(self.on_model_download_active)
        
        self.splitter.addWidget(self.settings_panel)
        self.settings_panel.setVisible(False)
        
        # Transcript Panel
        self.transcript_panel = TranscriptPanel(self.storage.base_dir, ICONS_DIR)
        self.transcript_panel.properties_clicked.connect(self.on_properties_clicked)
        self.transcript_panel.record_clicked.connect(self.on_record_clicked)
        self.transcript_panel.stop_recording_clicked.connect(self.on_stop_recording_confirmation)
        self.transcript_panel.force_capture_clicked.connect(self.on_force_capture_clicked)
        self.transcript_panel.pause_clicked.connect(self.on_pause_clicked)
        self.transcript_panel.summary_panel.summarize_clicked.connect(self.on_summarize_clicked)
        self.transcript_panel.quiz_clicked.connect(self.on_quiz_clicked)
        self.transcript_panel.import_clicked.connect(self.on_import_media_clicked)
        self.transcript_panel.import_pause_clicked.connect(self.on_import_pause_clicked)
        self.transcript_panel.import_stop_clicked.connect(self.on_import_stop_clicked)
        self.transcript_panel.capture_deleted.connect(self.storage.delete_capture)

        # Give the title-bar the transcript's panel toggle buttons.
        self.titleBar.add_panel_buttons([
            self.transcript_panel.ocr_visibility_button,
            self.transcript_panel.speech_visibility_button,
            self.transcript_panel.summary_visibility_button,
        ])

        ## Translate / define on a text selection in any panel
        self.transcript_panel.ocr_panel.lookup_requested.connect(self.on_lookup_requested)
        self.transcript_panel.speech_panel.lookup_requested.connect(self.on_lookup_requested)
        self.transcript_panel.summary_panel.lookup_requested.connect(self.on_lookup_requested)
        
        ## When any content is changed
        self.transcript_panel.ocr_panel.immediate_change.connect(self.unsaved_changes)
        self.transcript_panel.speech_panel.immediate_change.connect(self.unsaved_changes)
        self.transcript_panel.summary_panel.immediate_change.connect(self.unsaved_changes)

        ## Saved Changes
        self.transcript_panel.ocr_panel.ocr_text_changed.connect(lambda cid, text: self.on_text_changed(cid, text, 1))
        self.transcript_panel.speech_panel.speech_text_changed.connect(lambda cid, text: self.on_text_changed(cid, text, 2))
        self.transcript_panel.summary_panel.summary_text_changed.connect(self._on_summary_text_changed)

        self.splitter.addWidget(self.transcript_panel)
        
        # Properties Panel (created once with a placeholder session)
        self.properties_panel = None 
        
        # Recording Panel
        self.recording_panel = RecordingPanel(ICONS_DIR)
        self.recording_panel.cancel_clicked.connect(self.on_record_cancelled)
        self.recording_panel.record_clicked.connect(lambda data: self.on_recording_confirmed(data))
        
        self.splitter.addWidget(self.recording_panel)  # add this
        self.recording_panel.setVisible(False)

        # Quiz Panel (created once; reconfigured on each open)
        self.quiz_panel = QuizPanel()
        self.quiz_panel.generate_requested.connect(self.on_quiz_generate)
        self.quiz_panel.completed.connect(self.on_quiz_completed)
        self.quiz_panel.exit_requested.connect(self.on_quiz_exit)
        self.splitter.addWidget(self.quiz_panel)
        self.quiz_panel.setVisible(False)
        self._quiz_worker = None
        self.is_quizzing = False

        # Help Panel (created once; static content)
        self.help_panel = HelpPanel()
        self.help_panel.close_requested.connect(self.on_help_close)
        self.splitter.addWidget(self.help_panel)
        self.help_panel.setVisible(False)
        self.is_help_open = False

        # Size every panel so a newly added one doesn't leave the sidebar grabbing slack.
        self.splitter.setSizes([260] + [400] * (self.splitter.count() - 1)) # 1 : 4 ratio
        # Sidebar is fixed-width; content panels absorb resize.
        self.splitter.setStretchFactor(0, 0)
        for i in range(1, self.splitter.count()):
            self.splitter.setStretchFactor(i, 1)
        # Remember a user-dragged sidebar width so panel switches can restore it.
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        self.transcript_panel.set_session_locked(True) # Locked buttons initially

        # Load API keys and processing mode from saved settings
        self._load_api_keys()
        self._load_processing_mode()
        self._refresh_engine_labels()
        
        # Shortcuts Shift+1: Toggle sidebar (always active)
        self.sidebar_shortcut = QShortcut(QKeySequence("Shift+1"), self)
        self.sidebar_shortcut.activated.connect(self._toggle_sidebar)
        self.sidebar_shortcut.setEnabled(True)

        # Ctrl+T: New Session
        self.create_session_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self.create_session_shortcut.activated.connect(self.on_new_session_clicked)
        self.create_session_shortcut.setEnabled(True)
        
        # Ctrl+S: Settings
        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.settings_shortcut.activated.connect(self.on_settings_clicked)
        self.settings_shortcut.setEnabled(True)

        # Ctrl+G: Help and guide (always active)
        self.help_shortcut = QShortcut(QKeySequence("Ctrl+G"), self)
        self.help_shortcut.activated.connect(self.on_help_clicked)
        self.help_shortcut.setEnabled(True)

        # Ctrl+D: Properties
        self.properties_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.properties_shortcut.activated.connect(self.on_properties_clicked)
        self.properties_shortcut.setEnabled(False)
        
        # Ctrl+F: Recording panel
        self.recording_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.recording_shortcut.activated.connect(self.handle_record_shortcut)
        self.recording_shortcut.setEnabled(False)

        # Enter: Stop recording (with confirmation), only active while recording
        self.stop_recording_shortcut = QShortcut(QKeySequence("Return"), self)
        self.stop_recording_shortcut.activated.connect(self.on_stop_recording_confirmation)
        self.stop_recording_shortcut.setEnabled(False)

        # Ctrl+Enter: Force capture now, only active while recording
        self.capture_now_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.capture_now_shortcut.activated.connect(self.on_force_capture_clicked)
        self.capture_now_shortcut.setEnabled(False)

        # First-run onboarding: show Help guide instead of empty transcript.
        self._maybe_show_onboarding()

    def handle_record_shortcut(self) -> None:
        # Used by Ctrl + F
        if self.is_recording_open:
            self.on_record_cancelled()
        elif not self.is_recording:
            self.on_record_clicked()

    def _set_nav_locked(self, locked: bool) -> None:
        """Lock nav buttons during recording, import, summarize, or quiz."""
        self.sidebar.set_recording_locked(locked)
        self.titleBar.new_session_button.setDisabled(locked)
        self.titleBar.settings_button.setDisabled(locked)
        self.titleBar.help_button.setDisabled(locked)

    def _lock_nav_shortcuts(self, busy: bool, store_attr: str) -> None:
        """Disable nav shortcuts while busy, saving prior state to restore later."""
        shortcuts = (
            self.create_session_shortcut,
            self.settings_shortcut,
            self.properties_shortcut,
            self.recording_shortcut,
        )
        if busy:
            setattr(self, store_attr, {sc: sc.isEnabled() for sc in shortcuts})
            for sc in shortcuts:
                sc.setEnabled(False)
        else:
            for sc, was_enabled in getattr(self, store_attr, {}).items():
                sc.setEnabled(was_enabled)
            setattr(self, store_attr, {})

    def on_stop_recording_confirmation(self) -> None:
        if not self.is_recording:
            return
        reply = QMessageBox.question(
            self,
            "Stop Recording",
            "Stop the current recording?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_recording()

    def _activity_categories(self) -> list[str]:
        """Built-in defaults plus any custom activity categories already in use."""
        return merged_activity_categories(self.storage.get_activity_categories())

    def on_new_session_clicked(self) -> None:
        if self.is_new_session_open:
            self.new_session_panel.reset_form()
        else:
            # Pick up categories added since the panel was built (it's created once).
            self.new_session_panel.set_categories(
                self._activity_categories(), self.storage.get_module_categories()
            )

        self.is_new_session_open = not self.is_new_session_open
        self.is_properties_open = False # Close Properties when opening new session
        self.show_panel("new_session" if self.is_new_session_open else "transcript")
        
    def on_new_session_create(self, session_name, activity_category, module_category) -> None:
        current_time = datetime.now()
        new_session = Session(session_name, current_time, current_time, activity_category, 0, None, module_category, None, None)
        self.storage.create_session(new_session)
        # Select before refreshing so the new session's card comes back highlighted.
        self.current_session = new_session
        self._refresh_session_lists()

        # Clear the form so the next new session starts blank.
        self.new_session_panel.reset_form()

        self.is_new_session_open = not self.is_new_session_open
        self.show_panel("transcript")

        self.on_session_selected(self.current_session)
    
    def on_new_session_cancelled(self) -> None:
        self.is_new_session_open = False
        self.show_panel("transcript")
    
    def rebuild_properties_panel(self) -> None:
        if self.properties_panel:
            self.splitter.widget(self.splitter.indexOf(self.properties_panel)).setParent(None)
        self.properties_panel = PropertiesPanel(self.current_session, self._activity_categories(), self.storage.get_module_categories())
        self.properties_panel.delete_clicked.connect(self.on_properties_deleted)
        self.properties_panel.duplicate_clicked.connect(self.on_properties_duplicated)
        self.properties_panel.saved_clicked.connect(
            lambda n, c, g: self.on_properties_saved(n, c, g)
        )
        self.properties_panel.cancel_clicked.connect(self.on_properties_cancelled)
        self.splitter.addWidget(self.properties_panel)
        self.splitter.setStretchFactor(self.splitter.indexOf(self.properties_panel), 1)
    
    def on_session_selected(self, session: Session) -> None:
        self.current_session = session
        captures = self.storage.get_captures_by_session(session.id)
        # Block stale saves while panels repopulate.
        self._load_guard_until = time.monotonic() + 1.0
        self.transcript_panel.load_session(session, captures)
        
        # Close new session panel if its opened
        if self.is_new_session_open:
            self.is_new_session_open = False
                
        # Close the settings panel if its opened
        if self.is_settings_open:
            self.settings_panel.revert_theme()
            self.is_settings_open = False
                
        if self.is_properties_open:
            self.rebuild_properties_panel()
            self.show_panel("properties")
        else:
            self.show_panel("transcript")
        
        self.properties_shortcut.setEnabled(True)
        self.recording_shortcut.setEnabled(True)
        # load_session re-enables Record; keep it disabled if a download is still blocking.
        self._apply_record_download_lock()

    def start_recording(self, interval, region, monitor, device, hwnd=None) -> None:
        start_time = time.time()
        self.recording_start_time = start_time
        self._pending_speech = ""
        self._pending_capture_id = None

        # Start timer when capture actually begins (not during overlay selection).
        self.elapse_s = 0
        self.transcript_panel.recording_time_label.setText("00:00")
        self.timer.start(1000)

        # Create ocr worker thread
        self.ocr_worker = OCRWorker(
            self.current_session.id, self.storage.base_dir, interval, region, monitor, start_time, self.current_session.length, hwnd=hwnd,
            ocr_api_key=self._effective_api_key("ocr")
        )
        self.ocr_worker.capture_ready.connect(self.on_capture_ready)
        self.ocr_worker.engine_fallback.connect(self._on_ocr_engine_fallback)
        self.ocr_worker.api_error.connect(self._on_api_error)
        self.ocr_worker.start()
        
        # Window-only loopback captures just that window's audio, excluding other apps.
        loopback_pid = None
        if hwnd and isinstance(device, dict) and device.get("type") == "loopback":
            from core.process_loopback import pid_from_hwnd
            loopback_pid = pid_from_hwnd(hwnd)

        # Create audio worker thread
        self.audio_worker = AudioWorker(
            self.current_session.id, self.storage.base_dir, interval, device, start_time, self.current_session.length,
            speech_api_key=self._effective_api_key("speech"),
            speech_model=str(self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)),
            loopback_pid=loopback_pid,
        )
        self.audio_worker.chunk_ready.connect(self.on_chunk_ready)
        self.audio_worker.chunk_pending.connect(self.on_chunk_pending)
        self.audio_worker.engine_fallback.connect(self._on_speech_engine_fallback)
        self.audio_worker.api_error.connect(self._on_api_error)
        self.audio_worker.start()

        # Update footer to show live engine names
        self.transcript_panel.update_engine_labels(
            self.ocr_worker.engine_name,
            self._speech_engine_label(),
        )

        # Warn if API mode selected but no key; workers fall back to local.
        if self.processing_mode == "api" and not self.api_key:
            self.transcript_panel.show_connection_warning(SHORT_STATUS["no_key"])
        else:
            self.transcript_panel.clear_connection_warning()

        # Play sound effect
        self._play_effect(self.start_audio)
        
        # Enable recording-only shortcuts, disable the rest
        self.create_session_shortcut.setEnabled(False)
        self.settings_shortcut.setEnabled(False)
        self.properties_shortcut.setEnabled(False)
        self.recording_shortcut.setEnabled(False)
        self.stop_recording_shortcut.setEnabled(True)
        self.capture_now_shortcut.setEnabled(True)

    def on_pause_clicked(self) -> None:
        # Toggle pause on an active recording: freeze the timer + capture, or resume both.
        if not self.is_recording:
            return
        self.is_paused = not self.is_paused
        self.ocr_worker.set_paused(self.is_paused)
        self.audio_worker.set_paused(self.is_paused)
        self.transcript_panel.set_paused(self.is_paused)
        # Capture Now is meaningless while paused; gate its shortcut to match the button.
        self.capture_now_shortcut.setEnabled(not self.is_paused)

    def update_timer(self) -> None:
        # Hold the clock while paused so it shows only active recording time.
        if self.is_recording and not self.is_paused:
            self.elapse_s += 1
            self.transcript_panel.recording_time_label.setText(
                FormatClock(self.elapse_s, pad_minutes=True)
            )

    def on_record_aborted(self) -> None:
        self.is_recording = False
        self.is_paused = False
        self.timer.stop()
        self.elapse_s = 0
        
        self.transcript_panel.recording_time_label.setText("00:00")
        self.transcript_panel.record_button.setText("Record")
        self.transcript_panel.set_recording_active(False)
        self._set_nav_locked(False)
        self.transcript_panel.set_properties_locked(False)
        self.showNormal()

    def show_overlay(self, data) -> None:
        def on_region_selected(x, y, w, h):
            self.showNormal()
            self.start_recording(
                data["interval"], {"left": x, "top": y, "width": w, "height": h},
                data["monitor"], data["audio_device"], hwnd=data.get("hwnd"),
            )

        if data.get("hwnd"):
            self.overlay = CaptureOverlay(on_region_selected, self.on_record_aborted,
                                          hwnd=data["hwnd"])
        else:
            self.overlay = CaptureOverlay(on_region_selected, self.on_record_aborted,
                                          monitor_index=data["monitor"])
        self.show_panel("transcript")

    def _local_recording_blocked(self) -> bool:
        """Block local recording while a model download holds the lock; API speech is unaffected."""
        return self._model_download_active and not self._effective_api_key("speech")

    def _any_model_installed(self) -> bool:
        """True if a speech model that local recording will use is ready in the HF cache."""
        from pathlib import Path
        from huggingface_hub import try_to_load_from_cache
        from ui.settings_panel import SPEECH_MODEL_REPOS
        model_id = self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)
        repo = SPEECH_MODEL_REPOS.get(model_id)
        if not repo:
            return False
        try:
            path = try_to_load_from_cache(repo, "model.bin")
            return isinstance(path, str) and Path(path).is_file() and Path(path).stat().st_size > 0
        except Exception:
            return False

    def _apply_record_download_lock(self) -> None:
        """Disable Record during model download; restore when session is loaded and idle."""
        btn = self.transcript_panel.record_button
        if self._local_recording_blocked():
            btn.setDisabled(True)
            btn.setToolTip("Downloading speech model… recording is available once it finishes")
        else:
            if (self.current_session is not None and not self.is_recording
                    and self._summarize_worker is None):
                btn.setDisabled(False)
            btn.setToolTip("Open recording panel (Ctrl+F)")

    def on_model_download_active(self, active: bool) -> None:
        self._model_download_active = active
        self._apply_record_download_lock()

    def on_record_clicked(self) -> None:
        if not self.current_session:
            print('Need to select session first')
            return
        if self._local_recording_blocked():
            QMessageBox.information(
                self, "Speech model downloading",
                "A speech model is still downloading. Local recording will be available "
                "once it finishes, or switch Audio to the Gemini API in Settings."
            )
            return
        # If speech will run locally and no model is cached, show the banner so the user knows they need to download one first.
        if not self._effective_api_key("speech") and not self._any_model_installed():
            model = self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)
            self.transcript_panel.show_connection_warning(
                f"No speech model found ({model}). Download it in Settings to record locally."
            )
            return
        if not self.is_recording:
            self.show_panel("recording")
            self.is_recording_open = True
            
            # Reset the values
            self.recording_panel.reload_state()
            self.recording_panel.reload_sources()  # pick up newly-opened windows/devices
            self.recording_panel.load_preferences()
            self.is_properties_open = False # Close Properties when opening recording

    def on_recording_confirmed(self, data) -> None:
        if self.recording_panel.validate() is not None:
            return
        
        self.is_recording = True
        self.is_recording_open = False
        self.transcript_panel.record_button.setText("Recording") # Update Label
        self.transcript_panel.set_recording_active(True)
        
        # Lock Buttons
        self._set_nav_locked(True)
        self.transcript_panel.set_properties_locked(True)

        # Start the OCR and Audio threads
        if data["capture_option"] == "Mouse Select":
            self.showMinimized()
            QTimer.singleShot(300, lambda: self.show_overlay(data))
        else:
            self.show_panel("transcript")
            self.start_recording(data["interval"], data["region"], data["monitor"], data["audio_device"], hwnd=data.get("hwnd"))

    def stop_recording(self) -> None:
        self.show_panel("transcript")
        # Capture active time before resetting (elapse_s pauses while paused).
        self.timer.stop()
        recorded_seconds = self.elapse_s
        self.elapse_s = 0

        self.is_recording = False
        self.is_paused = False
        self._play_effect(self.stop_audio)
        
        # Update labels
        self.transcript_panel.recording_time_label.setText("00:00")
        self.transcript_panel.record_button.setText("Record")
        self.transcript_panel.set_recording_active(False)
        self.transcript_panel.clear_connection_warning()  # warning is recording-only
        
        # Unlock inputs
        self._set_nav_locked(False)
        self.transcript_panel.set_properties_locked(False)

        # Stop the threads
        self.ocr_worker.stop()
        self.audio_worker.stop()
        self.ocr_worker.wait()
        self.audio_worker.wait()

        # Drain queued signals then rescue any orphan speech.
        QApplication.processEvents()
        if self._pending_speech:
            # Stamp orphan speech at the pre-recording length, not 0.0, for correct timeline order.
            orphan = OCRCapture(float(self.current_session.length), "", "", None, self.current_session.id, self._pending_speech)
            self.storage.create_ocr_capture(orphan)
            self.transcript_panel.ocr_panel.add_capture(orphan)
            self.transcript_panel.speech_panel.add_capture(orphan)
            self._pending_speech = ""

        # Save total length (active time only, excludes any paused spans)
        self.current_session.length += recorded_seconds
        self.storage.update_session(self.current_session)
        
        # Assuming that recording will always give content, enable the summarize
        has_content = self.transcript_panel.ocr_panel.has_content() or self.transcript_panel.speech_panel.has_content()
        self.transcript_panel.summary_panel.summary_button.setDisabled(not has_content)
        self.transcript_panel.summary_panel.summary.setReadOnly(not has_content)
        # Quiz gated on summary existence.
        self.transcript_panel.set_quiz_available(bool(self.current_session.summary))
        
        # Shortcut
        self.create_session_shortcut.setEnabled(True)
        self.settings_shortcut.setEnabled(True)
        self.properties_shortcut.setEnabled(True)
        self.recording_shortcut.setEnabled(True)
        self.stop_recording_shortcut.setEnabled(False)
        self.capture_now_shortcut.setEnabled(False)
        
    def on_force_capture_clicked(self) -> None:
        if self.is_recording and hasattr(self, 'ocr_worker'):
            self.ocr_worker.force_capture()

    def on_record_cancelled(self) -> None:
        self.show_panel("transcript")
        self.is_recording_open = False

    # Media import

    def on_import_media_clicked(self) -> None:
        """Pick a local media file and transcribe it into the session."""
        if not self.current_session:
            print("Need to select session first")
            return
        # Don't allow importing while recording or while another import is running, and
        if self.is_recording or self._import_worker is not None:
            return
        if self._local_recording_blocked():
            QMessageBox.information(
                self, "Speech model downloading",
                "A speech model is still downloading. Importing transcribes through the "
                "same engine, so try again once it finishes, or switch Audio to the "
                "Gemini API in Settings."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Import media file", "",
            "Media files (*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.mp4 *.m4v *.mov *.avi *.mkv *.webm);;All files (*.*)"
        )
        if not path:
            return

        # Preview + pick the start point. Cancel aborts the whole import.
        from ui.media_import_dialog import MediaImportDialog
        dialog = MediaImportDialog(path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_media_import(path, dialog.start_seconds())

    def _set_import_locked(self, locked: bool) -> None:
        """Lock the app during import (same as recording)."""
        self._set_nav_locked(locked)
        self.transcript_panel.set_properties_locked(locked)
        # Disable the shortcuts that would otherwise bypass the locked buttons.
        self.create_session_shortcut.setEnabled(not locked)
        self.settings_shortcut.setEnabled(not locked)
        self.properties_shortcut.setEnabled(not locked)
        self.recording_shortcut.setEnabled(not locked)

    def _start_media_import(self, path: str, start_offset: float) -> None:
        # Each segment becomes its own capture card (10 s per card).
        interval = 10
        offset = self.current_session.length
        self._import_active = True
        self.is_paused = False
        self.transcript_panel.set_import_active(True)
        self._set_import_locked(True)
        self.transcript_panel.clear_connection_warning()
        # Footer clock tracks transcribed-media time (driven by progress).
        self.transcript_panel.recording_time_label.setText("00:00")

        self._import_worker = MediaImportWorker(
            self.current_session.id, self.storage.base_dir, interval, path,
            time.time(), offset,
            speech_api_key=self._effective_api_key("speech"),
            speech_model=str(self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)),
            ocr_api_key=self._effective_api_key("ocr"),
            start_offset=start_offset,
        )
        # Finished segments are reuse the recording signal path.
        self._import_worker.capture_ready.connect(self.on_capture_ready)
        self._import_worker.progress.connect(self.on_import_progress)
        self._import_worker.import_finished.connect(self.on_import_finished)
        self._import_worker.import_failed.connect(self.on_import_failed)
        # Footer engine labels: speech via inherited signal, OCR via imported forwarder.
        self._import_worker.engine_fallback.connect(self._on_speech_engine_fallback)
        self._import_worker.ocr_engine_fallback.connect(self._on_ocr_engine_fallback)
        self._import_worker.api_error.connect(self._on_api_error)
        self._import_worker.finished.connect(self._on_import_thread_done)
        self._import_worker.start()

        # Show the configured engines up front (the workers refine these as they resolve).
        self.transcript_panel.update_engine_labels(
            pretty_model(FREQUENT_MODEL_CHAIN[0]) if self._effective_api_key("ocr") else "pytesseract",
            self._speech_engine_label(),
        )

    def on_import_progress(self, processed_s: float, total_s: float) -> None:
        self.transcript_panel.set_import_progress(processed_s, total_s)
        # Run the footer clock off transcribed-media time so it "counts up" during import.
        self.transcript_panel.recording_time_label.setText(
            FormatClock(processed_s, pad_minutes=True)
        )

    def on_import_pause_clicked(self) -> None:
        if self._import_worker is None:
            return
        self.is_paused = not self.is_paused
        self._import_worker.set_paused(self.is_paused)
        self.transcript_panel.set_import_paused(self.is_paused)

    def on_import_stop_clicked(self) -> None:
        # Stop after the current segment; keeps everything transcribed so far. Teardown
        if self._import_worker is not None:
            self._import_worker.stop()
            self.transcript_panel.import_status.setText("Stopping…")

    def on_import_finished(self, transcribed_s: float) -> None:
        # Extend session length by transcribed span.
        self.current_session.length += int(transcribed_s)
        self.storage.update_session(self.current_session)

    def on_import_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Import failed", message)

    def _on_import_thread_done(self) -> None:
        # Worker thread has finished. Tear down and re-enable UI.
        self._import_worker = None
        self._import_active = False
        self.is_paused = False
        self.transcript_panel.set_import_active(False)
        self._set_import_locked(False)
        self.transcript_panel.recording_time_label.setText("00:00")
        # An import gives content, so summarize becomes available (quiz still needs a summary).
        has_content = (self.transcript_panel.ocr_panel.has_content()
                       or self.transcript_panel.speech_panel.has_content())
        self.transcript_panel.summary_panel.summary_button.setDisabled(not has_content)
        self.transcript_panel.summary_panel.summary.setReadOnly(not has_content)


    def on_capture_ready(self, capture: OCRCapture) -> None:
        self.storage.create_ocr_capture(capture)
        # Attach any speech that arrived before this slide was captured.
        if self._pending_speech:
            self.storage.append_speech_text(capture.id, self._pending_speech)
            capture.speech_text = (capture.speech_text or "") + self._pending_speech
            self._pending_speech = ""
        self.transcript_panel.ocr_panel.add_capture(capture)
        self.transcript_panel.speech_panel.add_capture(capture)

    def _resolve_speech_target(self, timestamp):
        """Latest slide at or before the speech timestamp, or earliest slide."""
        recent = self.storage.get_latest_capture_before(self.current_session.id, timestamp)
        return recent or self.storage.get_earliest_capture(self.current_session.id)

    def on_chunk_pending(self, timestamp) -> None:
        # A chunk is being transcribed; show placeholder on its target slide.
        if not self.current_session:
            return
        target = self._resolve_speech_target(timestamp)
        if target:
            self._pending_capture_id = target.id
            self.transcript_panel.speech_panel.show_pending(target.id)

    def on_chunk_ready(self, timestamp, text) -> None:
        if not self.current_session:
            return
        # Clear the placeholder we actually showed (id may differ from fresh lookup).
        if self._pending_capture_id is not None:
            self.transcript_panel.speech_panel.clear_pending(self._pending_capture_id)
            self._pending_capture_id = None
        if not text:
            return
        target = self._resolve_speech_target(timestamp)
        if target:
            self.storage.append_speech_text(target.id, text)
            self.transcript_panel.speech_panel.update_capture_speech(target.id, text)
        else:
            # Buffered until the first slide appears. Early narration isn't lost.
            self._pending_speech += text

    def on_lookup_requested(self, text: str, kind: str, target: str) -> None:
        """Translate or define a selection (right-clicked in any panel) via Gemini."""
        text = (text or "").strip()
        if not text:
            return
        # Lookups are Gemini-only; enabled whenever a key exists, regardless of the
        if not self.api_key:
            QMessageBox.information(
                self, "Gemini API key needed",
                "Add a Gemini API key in Settings to use Translate / Define."
            )
            return
        if kind == "translate" and not target:  # "Other..." means ask for a language
            target, ok = QInputDialog.getText(self, "Translate", "Translate to which language?")
            if not ok or not target.strip():
                return
            target = target.strip()

        title = f"Translation → {target}" if kind == "translate" else "Definition"
        if self._lookup_popup is None:
            from ui.lookup_popup import LookupPopup
            self._lookup_popup = LookupPopup(self, ICONS_DIR)
        self._lookup_popup.prepare(title, text)
        self._lookup_popup.show_at(QCursor.pos())

        from core.lookup import LookupWorker
        worker = LookupWorker(text, kind, target, self.api_key)
        self._lookup_worker = worker
        self._lookup_workers.add(worker)
        worker.done.connect(self._on_lookup_done)
        worker.failed.connect(self._on_lookup_failed)
        worker.finished.connect(lambda w=worker: self._lookup_workers.discard(w))
        worker.start()

    def _on_lookup_done(self, result: str) -> None:
        # Ignore a stale worker's result (the user started another lookup since).
        if self.sender() is self._lookup_worker and self._lookup_popup is not None:
            self._lookup_popup.set_result(result or "(no result)")

    def _on_lookup_failed(self, message: str) -> None:
        if self.sender() is self._lookup_worker and self._lookup_popup is not None:
            self._lookup_popup.set_error(message)

    def on_summarize_clicked(self) -> None:
        if not self.current_session:
            print('Need to select session first')
            return
        # Don't summarize mid-recording or re-click while already generating.
        if self.is_recording:
            return
        # Ignore re-clicks while a summary is already being generated.
        if self._summarize_worker is not None:
            return
        # Summarize is Gemini-only (works in both modes).
        if not self.api_key:
            QMessageBox.information(
                self, "Gemini API key needed",
                "Add a Gemini API key in Settings to generate a summary."
            )
            return

        captures = self.storage.get_captures_by_session(self.current_session.id)
        total_text = ""

        # Combine all the texts together
        for capture in captures:
            total_text += (capture.extracted_text or "") + (capture.speech_text or "")

        # Run on worker thread to keep UI responsive.
        button = self.transcript_panel.summary_panel.summary_button
        button.setDisabled(True)
        button.setText("Summarizing…")
        self._set_summarizing(True)

        self._summarize_worker = SummarizeWorker(total_text, api_key=self.api_key)
        self._summarize_worker.done.connect(self._on_summarize_done)
        self._summarize_worker.failed.connect(self._on_summarize_failed)
        self._summarize_worker.finished.connect(self._on_summarize_finished)
        self._summarize_worker.start()

    def _on_summarize_done(self, summarized_text, engine) -> None:
        current = self.transcript_panel.summary_panel.current_source()

        # If user has modified the summary, double confirm before overwrite.
        if current and summarized_text != current:
            reply = QMessageBox.question(
                self,
                "Summarized text modified",
                "Overwrite summarized text?"
            )
            if reply == QMessageBox.StandardButton.No:
                return
        # Avoid updating timestamp when summary text hasn't actually changed.
        elif summarized_text == current:
            return

        # Show the new markdown source (Preview button renders it).
        self.transcript_panel.summary_panel.set_summary(summarized_text)

        self.current_session.summary = summarized_text
        current_time = datetime.now()
        self.current_session.summary_generated_at = current_time
        self.current_session.date_modified = current_time
        self.storage.update_session(self.current_session)

    def _on_summarize_failed(self, message) -> None:
        print(f"[Summarize] failed: {message}")
        QMessageBox.warning(self, "Summarize failed", f"Could not generate summary:\n{message}")

    def _on_summarize_finished(self) -> None:
        # Re-enable regardless of success/failure.
        button = self.transcript_panel.summary_panel.summary_button
        button.setDisabled(False)
        button.setText("Summarize")
        self._set_summarizing(False)
        self._summarize_worker = None
        # _set_summarizing(False) re-enables the quiz button as part of unlocking; gate it
        self.transcript_panel.set_quiz_available(bool(self.current_session and self.current_session.summary))

    def _set_summarizing(self, busy: bool) -> None:
        """Lock the app during summarization; user can still scroll and toggle panels."""
        self._set_nav_locked(busy)
        # Workspace: properties, record, sync-scroll, and both feeds (read-only + no delete).
        self.transcript_panel.set_summary_lock(busy)
        self._lock_nav_shortcuts(busy, "_locked_shortcut_states")

    # Quiz

    def _combined_session_text(self) -> str:
        captures = self.storage.get_captures_by_session(self.current_session.id)
        parts = []
        for c in captures:
            if c.extracted_text:
                parts.append(c.extracted_text)
            if c.speech_text:
                parts.append(c.speech_text)
        if self.current_session.summary:
            parts.append(self.current_session.summary)
        return "\n".join(parts)

    def _parse_saved_quiz(self) -> list | None:
        raw = self.current_session.quiz if self.current_session else None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) and data else None
        except Exception:
            return None

    def _parse_saved_answers(self) -> list | None:
        """Return stored quiz answers, or None for older quizzes without persisted answers."""
        raw = self.current_session.quiz_answers if self.current_session else None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else None
        except Exception:
            return None

    def on_quiz_clicked(self) -> None:
        if not self.current_session or self.is_recording:
            return
        # Quiz is Gemini-only (works in both modes).
        if not self.api_key:
            QMessageBox.information(
                self, "Gemini API key needed",
                "Add a Gemini API key in Settings to generate a quiz."
            )
            return

        self._quiz_text = self._combined_session_text()
        self._quiz_hash = source_hash(self._quiz_text)

        saved = self._parse_saved_quiz()
        self.quiz_panel.set_saved_quiz(
            saved,
            self.current_session.quiz_score if saved else None,
            self._parse_saved_answers() if saved else None,
        )
        if saved:
            changed = self.current_session.quiz_source_hash != self._quiz_hash
            self.quiz_panel.configure_intro(True, self.current_session.quiz_score, len(saved), changed)
        else:
            self.quiz_panel.configure_intro(False, None, 0, False)

        self.is_quizzing = True
        self.is_properties_open = False  # quiz replaces the transcript/properties view
        self._set_quizzing(True)
        self.show_panel("quiz")

    def on_quiz_generate(self) -> None:
        if self._quiz_worker is not None:
            return
        self.quiz_panel.set_loading()
        self._quiz_worker = QuizWorker(self._quiz_text, self.api_key)
        self._quiz_worker.done.connect(self._on_quiz_generated)
        self._quiz_worker.failed.connect(self._on_quiz_failed)
        self._quiz_worker.attempting.connect(self.quiz_panel.set_generating_engine)
        self._quiz_worker.finished.connect(self._on_quiz_worker_finished)
        self._quiz_worker.start()

    def _on_quiz_generated(self, questions) -> None:
        # Persist the new quiz (resets the score) so it can be reviewed/retaken later.
        self.current_session.quiz = json.dumps(questions)
        self.current_session.quiz_source_hash = self._quiz_hash
        self.current_session.quiz_score = None
        self.current_session.quiz_generated_at = datetime.now()
        self.current_session.quiz_answers = None  # fresh quiz -> no recorded answers yet
        self.storage.save_quiz(self.current_session.id, self.current_session.quiz, self._quiz_hash)
        self.quiz_panel.set_saved_quiz(questions, None)
        self.quiz_panel.load_questions(questions)

    def _on_quiz_failed(self, message: str) -> None:
        self.quiz_panel.show_error(message)

    def _on_quiz_worker_finished(self) -> None:
        self._quiz_worker = None

    def on_quiz_completed(self, score: int, total: int) -> None:
        if not self.current_session:
            return
        # Persist the score AND the per-question answers so Review can show what the
        answers_json = json.dumps(self.quiz_panel.current_answers())
        self.current_session.quiz_score = score
        self.current_session.quiz_answers = answers_json
        self.storage.update_quiz_result(self.current_session.id, score, answers_json)

    def on_quiz_exit(self) -> None:
        if self.quiz_panel.is_answering():
            reply = QMessageBox.question(
                self, "Exit quiz", "Leave the quiz? Your progress on this attempt won't be saved."
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.is_quizzing = False
        self._set_quizzing(False)
        self.show_panel("transcript")

    def _set_quizzing(self, busy: bool) -> None:
        """Lock the app during quiz (like summarizing)."""
        self._set_nav_locked(busy)
        self._lock_nav_shortcuts(busy, "_quiz_locked_shortcuts")

    def on_search_changed(self, text) -> None:
        self.filter_name = text
        self.apply_filters()

    def on_category_filter_changed(self, category) -> None:
        self.filter_category = category
        self.apply_filters()

    def on_module_filter_changed(self, module) -> None:
        self.filter_module = module
        self.apply_filters()

    def apply_filters(self) -> None:
        sessions = self.storage.search_sessions(self.filter_name, self.filter_category, self.filter_module)
        self.sidebar.refresh(sessions, self._selected_session_id())

    def _selected_session_id(self):
        return self.current_session.id if self.current_session else None

    def _refresh_session_lists(self) -> None:
        """Rebuild sidebar and export dropdown after session changes."""
        sessions = self.storage.get_all_sessions()
        self.sidebar.refresh(sessions, self._selected_session_id())
        self.sidebar.update_categories(self._activity_categories(), self.storage.get_module_categories())
        self.settings_panel.refresh_sessions(sessions)
        
    def on_properties_clicked(self) -> None:
        self.is_properties_open = not self.is_properties_open
        if self.is_properties_open:
            self.rebuild_properties_panel()
        self.show_panel("properties" if self.is_properties_open else "transcript")
    
    def on_properties_cancelled(self) -> None:
        self.is_properties_open = False
        self.show_panel("transcript")

    def on_properties_saved(self, session_name, activity_category, module_category) -> None:        
        # Used data to update session info
        self.current_session.name = session_name
        self.transcript_panel.session_name.setText(session_name)
        self.current_session.date_modified = datetime.now()
        self.current_session.activity_category = activity_category
        self.current_session.module_category = module_category
        self.storage.update_session(self.current_session)
        self._refresh_session_lists()

    def on_properties_deleted(self) -> None:
        self.is_properties_open = not self.is_properties_open
        self.properties_panel.setVisible(self.is_properties_open)
        self.storage.delete_session(self.current_session.id)
        # Drop reference to deleted session.
        self.current_session = None
        self._refresh_session_lists()
        self.transcript_panel.clear_panels()

    def on_properties_duplicated(self) -> None:
        self.current_session = self.storage.duplicate_sessions(self.current_session.id)
        self._refresh_session_lists()
        self.on_session_selected(self.current_session)
    
    def unsaved_changes(self) -> None:
        self.transcript_panel.saved_label.setText("Unsaved")

    def _on_summary_text_changed(self, text: str) -> None:
        # Guarded here (not a lambda dereferencing current_session.id at connect
        if self.current_session:
            self.on_text_changed(self.current_session.id, text, 3)

    def on_text_changed(self, id, text, option: int) -> None:
        # Debounced saves can fire after session deletion; guard against missing session.
        if not self.current_session:
            return
        # Still in the post-load grace window — skip.
        if time.monotonic() < self._load_guard_until:
            return
        now = datetime.now()
        self.current_session.date_modified = now
        
        # Change OCR or Speech or Summary Text 
        if option == 1:
            self.storage.update_extracted_text(id, text)
        elif option == 2:
            self.storage.update_speech_text(id, text)
        elif option == 3:
            self.current_session.summary = text
        # Quiz gated on having a summary with non-empty text.
            self.transcript_panel.set_quiz_available(bool(text and text.strip()))

        self.storage.update_session(self.current_session)
        # Don't rebuild sidebar on every keystroke. Refresh on next navigation.
        self.transcript_panel.saved_label.setText("Saved")

    def on_settings_clicked(self) -> None:
        if self.is_settings_open:
            self.settings_panel.load_settings()
        
        self.is_settings_open = not self.is_settings_open
        self.is_properties_open = False # Close Properties when opening settings
        if self.is_settings_open:
        # Re-enumerate windows/devices, then restore saved defaults.
            self.settings_panel.reload_sources()
            self.settings_panel.load_settings()
            self.settings_panel.update_ui()
        self.show_panel("settings" if self.is_settings_open else "transcript")

    def on_help_clicked(self) -> None:
        self.is_help_open = not self.is_help_open
        if self.is_help_open:
            self.is_properties_open = False  # help takes over the workspace view
        self.show_panel("help" if self.is_help_open else "transcript")

    def on_help_close(self) -> None:
        self.is_help_open = False
        self.show_panel("transcript")

    def on_settings_help_requested(self) -> None:
        """Open Help at the API-key chapter."""
        self.show_panel("help")
        QTimer.singleShot(0, self.help_panel.scroll_to_api_key)

    def _maybe_show_onboarding(self) -> None:
        """On first launch, open Help guide instead of empty transcript; one-time redirect via QSettings."""
        if self.settings.value("onboarding_seen", False, type=bool):
            return
        # Record we've shown onboarding before navigating to prevent crash loops.
        self.settings.setValue("onboarding_seen", True)
        self.settings.sync()
        self.show_panel("help")

    def _load_api_keys(self) -> None:
        self.api_key = str(self.settings.value("api_key_gemini", ""))

    def _load_processing_mode(self) -> None:
        self.processing_mode = str(self.settings.value("processing_mode", "local"))

    def _effective_api_key(self, kind: str = "") -> str:
        # API used only when master switch is on AND per-engine toggle is enabled.
        if self.processing_mode != "api":
            return ""
        if kind and not self.settings.value(f"api_use_{kind}", True, type=bool):
            return ""
        return self.api_key

    def _speech_engine_label(self) -> str:
        """Speech engine label before model loads; engine_fallback upgrades it with resolved model + device."""
        if self._effective_api_key("speech"):
            return pretty_model(FREQUENT_MODEL_CHAIN[0])
        return f"faster-whisper · {self.settings.value('speech_model', DEFAULT_SPEECH_MODEL)}"

    def _refresh_engine_labels(self) -> None:
        ocr_engine = pretty_model(FREQUENT_MODEL_CHAIN[0]) if self._effective_api_key("ocr") else "pytesseract"
        # Mid-recording, don't downgrade worker-reported labels with config state.
        if self.is_recording and not self._effective_api_key("speech"):
            speech_engine = self.transcript_panel.speech_engine_label.text()
        else:
            speech_engine = self._speech_engine_label()
        self.transcript_panel.update_engine_labels(ocr_engine, speech_engine)

    def _on_ocr_engine_fallback(self, engine: str) -> None:
        self.transcript_panel.update_engine_labels(
            engine,
            self.transcript_panel.speech_engine_label.text(),
        )
        self._maybe_clear_api_warning(engine)

    def _on_speech_engine_fallback(self, engine: str) -> None:
        self.transcript_panel.update_engine_labels(
            self.transcript_panel.ocr_engine_label.text(),
            engine,
        )
        self._maybe_clear_api_warning(engine)

    def _on_api_error(self, status: str) -> None:
        """Show red banner on API failure mid-recording/import."""
        if not self.is_recording and not self._import_active:
            return
        self.transcript_panel.show_connection_warning(
            SHORT_STATUS.get(status, "Connection problem")
        )

    def _maybe_clear_api_warning(self, engine: str) -> None:
        # An API engine reporting in means connection/key is working.
        if engine.lower().startswith("gemini"):
            self.transcript_panel.clear_connection_warning()

    def on_processing_mode_changed(self, mode: str) -> None:
        self.processing_mode = mode
        self._refresh_engine_labels()
        # Switching Audio between local and Gemini changes whether a download blocks Record.
        self._apply_record_download_lock()

    def on_api_keys_changed(self, key: str) -> None:
        self.api_key = key
        self._load_processing_mode()
        self._refresh_engine_labels()

    def _on_theme_changed(self, theme: str) -> None:
        refresh_icons(self, theme)
        self.sidebar.refresh_theme(theme)
        self.help_panel.refresh_theme(theme)

    def _play_effect(self, player: QMediaPlayer) -> None:
        if not player.source().isEmpty():
            player.stop()
            player.play()

    def on_sound_effects_changed(self, start: str, stop: str) -> None:
        self.start_audio.setSource(QUrl.fromLocalFile(start) if start else QUrl())
        self.stop_audio.setSource(QUrl.fromLocalFile(stop) if stop else QUrl())
        
        self.settings.setValue("start_sound", start)
        self.settings.setValue("stop_sound", stop)

    def on_export_clicked(self, session_id: int) -> None:
        if not session_id:
            return

        session = self.storage.get_session(session_id)
        captures = self.storage.get_captures_by_session(session_id)
        
        path, _ = QFileDialog.getSaveFileName(self, "Export Session", session.name, "ZIP Files (*.zip)")
        if not path:
            return
        
        session_data = {
            "name": session.name,
            "activity_category": session.activity_category,
            "module_category": session.module_category,
            "date_recorded": session.date_recorded.isoformat(),
            "date_modified": session.date_modified.isoformat(),
            "length": session.length,
            "summary": session.summary,
            "summary_generated_at": session.summary_generated_at.isoformat() if session.summary_generated_at else None,
            "quiz": session.quiz,
            "quiz_score": session.quiz_score,
            "quiz_source_hash": session.quiz_source_hash,
            "quiz_generated_at": session.quiz_generated_at.isoformat() if session.quiz_generated_at else None,
            "quiz_answers": session.quiz_answers,
            "captures": [
                {
                    "timestamp": c.timestamp,
                    "image_path": c.image_path,
                    "extracted_text": c.extracted_text,
                    "speech_text": c.speech_text
                }
                for c in captures
            ]
        }
        
        captures_dir = Path(self.storage.base_dir) / 'sessions' / str(session_id) / 'captures'
        
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr("session.json", json.dumps(session_data, indent=2))
            for capture in captures:
                if not capture.image_path:
                    continue  # speech-only capture with no screenshot
                img = captures_dir / capture.image_path
                if img.exists():
                    zf.write(img, f"captures/{capture.image_path}")
    
    def on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Session", "", "ZIP Files (*.zip)")
        if not path:
            return
        
        with zipfile.ZipFile(path, 'r') as zf:
            session_data = json.loads(zf.read("session.json"))
            
        # Archives exported before the activity_category rename carry old key.
            new_session = Session(
                name=session_data["name"],
                activity_category=session_data.get(
                    "activity_category", session_data.get("session_category", "")),
                module_category=session_data.get("module_category"),
                date_recorded=datetime.fromisoformat(session_data["date_recorded"]),
                date_modified=datetime.now(),
                length=session_data["length"],
                summary=session_data.get("summary"),
                summary_generated_at=datetime.fromisoformat(session_data["summary_generated_at"]) if session_data.get("summary_generated_at") else None,
                quiz=session_data.get("quiz"),
                quiz_score=session_data.get("quiz_score"),
                quiz_source_hash=session_data.get("quiz_source_hash"),
                quiz_generated_at=datetime.fromisoformat(session_data["quiz_generated_at"]) if session_data.get("quiz_generated_at") else None,
                quiz_answers=session_data.get("quiz_answers"),
                id=None
            )
            new_id = self.storage.create_session(new_session)
            
            # Copy images into new session folder
            captures_dir = Path(self.storage.base_dir) / 'sessions' / str(new_id) / 'captures'
            for capture_data in session_data["captures"]:
                zip_img_path = f"captures/{capture_data['image_path']}"
                if zip_img_path in zf.namelist():
                    zf.extract(zip_img_path, Path(self.storage.base_dir) / 'sessions' / str(new_id))
                
                capture = OCRCapture(
                    timestamp=capture_data["timestamp"],
                    image_path=capture_data["image_path"],
                    extracted_text=capture_data["extracted_text"],
                    speech_text=capture_data.get("speech_text"),
                    session_id=new_id,
                    id=None
                )
                self.storage.create_ocr_capture(capture)
        self._refresh_session_lists()

    def on_all_deleted_clicked(self) -> None:
        self.storage.delete_all_sessions()
        self.current_session = None
        self._refresh_session_lists()
        self.transcript_panel.clear_panels()

    def show_panel(self, panel: str) -> None:
        # Revert theme if leaving settings without saving.
        if self.is_settings_open and panel != "settings":
            self.settings_panel.revert_theme()

        # Help borrows sidebar width; restore when help closes.
        help_was_open = not self.help_panel.isHidden()
        if panel == "help" and not help_was_open:
            self._sidebar_open_before_help = not self.sidebar.isHidden()
            if self._sidebar_open_before_help:
                self._sidebar_width = self.splitter.sizes()[0]
                self.sidebar.setVisible(False)
        elif panel != "help" and help_was_open and self._sidebar_open_before_help:
            self.sidebar.setVisible(True)
            sizes = self.splitter.sizes()
            sizes[0] = self._sidebar_width
            self.splitter.setSizes(sizes)

        # "transcript", "settings", "new_session", "recording", "properties", "quiz", "help"
        self.transcript_panel.setVisible(panel == "transcript")
        self.settings_panel.setVisible(panel == "settings")
        self.new_session_panel.setVisible(panel == "new_session")
        self.recording_panel.setVisible(panel == "recording")
        self.quiz_panel.setVisible(panel == "quiz")
        self.help_panel.setVisible(panel == "help")
        # Sync all panel flags so switching doesn't leave stale state.
        self.is_settings_open = (panel == "settings")
        self.is_new_session_open = (panel == "new_session")
        self.is_help_open = (panel == "help")
        self.is_properties_open = (panel == "properties")

        if self.properties_panel:
            # Properties shows alongside transcript
            self.properties_panel.setVisible(panel == "properties")
            if panel == "properties":
                self.transcript_panel.setVisible(True)

        # Qt splitter sometimes leaves a newly-visible panel at 0 width.
        QTimer.singleShot(0, self._ensure_content_visible)

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        # User drag: capture sidebar width to restore later.
        if self.sidebar.isVisible():
            self._sidebar_width = self.splitter.sizes()[0]

    def _ensure_content_visible(self) -> None:
        sizes = self.splitter.sizes()
        total = self.splitter.width()
        visible_content = [i for i in range(1, self.splitter.count())
                           if self.splitter.widget(i).isVisible()]
        if total <= 0 or not visible_content:
            return
        changed = False

        # Pin sidebar width; absorb drift into the widest visible content panel.
        if self.sidebar.isVisible() and sizes[0] != self._sidebar_width:
            delta = sizes[0] - self._sidebar_width
            sizes[0] = self._sidebar_width
            widest = max(visible_content, key=lambda i: sizes[i])
            sizes[widest] = max(0, sizes[widest] + delta)
            changed = True

        # If content panels collapsed to 0, hand leftover to first visible one.
        if sum(sizes[i] for i in visible_content) == 0:
            sizes[visible_content[0]] = max(0, total - sizes[0])
            changed = True

        if changed:
            self.splitter.setSizes(sizes)

    def _toggle_sidebar(self) -> None:
        if self.sidebar.isVisible():
            self._sidebar_width = self.splitter.sizes()[0]
            self.sidebar.setVisible(False)
        else:
            self.sidebar.setVisible(True)
            sizes = self.splitter.sizes()
            sizes[0] = self._sidebar_width
            self.splitter.setSizes(sizes)

    def _restore_window_state(self) -> None:
        # restoreGeometry replays size, position, and maximized state; no showMaximized() needed.
        geometry = self.settings.value("windowGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _save_window_state(self) -> None:
        # Save unconditionally; saveGeometry encodes maximized state, so one call captures everything.
        self.settings.setValue("windowGeometry", self.saveGeometry())

    def _shutdown_background_workers(self) -> None:
        """Stop running worker threads before window destruction."""
        workers = [self._summarize_worker, self._quiz_worker,
                   *self._lookup_workers, *self.settings_panel.active_workers()]
        for worker in workers:
            if worker is None or not worker.isRunning():
                continue
            if not worker.wait(2000):
                worker.terminate()
                worker.wait(1000)
        self._summarize_worker = None
        self._quiz_worker = None

    def closeEvent(self, event) -> None:
        if self._model_download_active:
            reply = QMessageBox.question(
                self,
                "Speech model downloading",
                "A speech model is still downloading. Close anyway and cancel the download?"
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        if self._summarize_worker is not None:
            reply = QMessageBox.question(
                self,
                "Summary in progress",
                "A summary is still being generated. Closing now will cancel it. Close anyway?"
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # Detach handlers so late results don't fire against torn-down widgets.
            try:
                self._summarize_worker.done.disconnect()
                self._summarize_worker.failed.disconnect()
                self._summarize_worker.finished.disconnect()
            except TypeError:
                pass

        if self._import_worker is not None:
            reply = QMessageBox.question(
                self,
                "Import in progress",
                "A media import is still transcribing. Stop it and close? "
                "Everything transcribed so far is kept."
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # Finish the segment in flight, then join before the window is destroyed.
            self._import_worker.stop()
            self._import_worker.wait()

        if self.is_recording:
            reply = QMessageBox.question(
                self,
                "Recording in progress",
                "Stop recording and close?"
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.ocr_worker.stop()
            self.audio_worker.stop()
            self.ocr_worker.wait()
            self.audio_worker.wait()

        # Quiz generation, lookups, connection tests, model downloads: bring threads down.
        self._shutdown_background_workers()
        self.storage.close()
        self._save_window_state()
        event.accept()