import time
import zipfile, json

from qframelesswindow import FramelessMainWindow
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QApplication, QInputDialog
from ui.grip_splitter import GripSplitter
from PyQt6.QtGui import QShortcut, QKeySequence, QGuiApplication, QCursor
from PyQt6.QtCore import Qt, QTimer, QUrl, QSettings
from PyQt6.QtMultimedia import QSoundEffect

from pathlib import Path
from datetime import datetime

from models.lecture import Session, OCRCapture
from storage.database import Storage
from core.ocr import OCRWorker
from core.audio import AudioWorker, DEFAULT_SPEECH_MODEL
from core.summarizer import SummarizeWorker
from ui.title_bar import CustomTitleBar
from ui.capture_overlay import CaptureOverlay
from ui.sidebar import Sidebar
from ui.new_session_panel import NewSessionPanel
from ui.transcript_panel import TranscriptPanel
from ui.properties_panel import PropertiesPanel
from ui.recording_panel import RecordingPanel
from ui.settings_panel import SettingsPanel
from ui.styles import load_icon, refresh_icons

BASE_DIR = Path(__file__).resolve().parent
BUNDLED_SOUNDS_DIR = BASE_DIR.parent / 'assets' / 'sound_effects'
ICONS_DIR = BASE_DIR.parent / 'assets' / 'icons'
THEMES_DIR = BASE_DIR.parent / 'assets' / 'themes'

class MainWindow(FramelessMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()
        self.settings = QSettings("LectureCapture", "LectureCapture")
        # Migrate the retired "auto" speech model to a concrete default. Detect Hardware
        # now sets the model explicitly instead of resolving "auto" on every recording.
        if str(self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)) == "auto":
            self.settings.setValue("speech_model", DEFAULT_SPEECH_MODEL)
        self.current_session = None
        self.is_recording = False
        self.is_new_session_open = False
        self.is_settings_open = False
        self.is_properties_open = False
        self.is_recording_open = False

        # Speech that arrived before any slide was captured, held until the first
        # capture exists so early narration isn't lost (see on_chunk_ready).
        self._pending_speech = ""
        # Capture currently showing the "transcribing…" placeholder (one chunk is in
        # flight at a time). Tracked so we clear exactly the one we showed.
        self._pending_capture_id = None

        # On-demand translate/define lookups: one reusable popup card, plus a set that
        # keeps in-flight workers alive until they finish (so none is GC'd mid-run).
        self._lookup_popup = None
        self._lookup_worker = None
        self._lookup_workers = set()

        # Background summarization runs on a worker thread so the (often slow) API
        # call doesn't freeze the UI. Held here so the QThread isn't garbage-collected
        # mid-run, and to prevent overlapping summarize requests.
        self._summarize_worker = None

        # Window details
        self.setWindowIcon(load_icon(ICONS_DIR / 'logo.png'))
        self.setWindowTitle("LectureCapture")
        self.setMinimumSize(800, 600)
        self.resize(1300, 800)
        
        # Move it to the middle
        screen = QGuiApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())
        
        # Default Sound Effects
        self.DEFAULT_START_SOUND = str(BUNDLED_SOUNDS_DIR / 'Beep 1 (Default).wav')
        self.DEFAULT_STOP_SOUND = str(BUNDLED_SOUNDS_DIR / 'Chirp 1 (Default).wav')

        start_path = self.settings.value("start_sound", self.DEFAULT_START_SOUND)
        stop_path = self.settings.value("stop_sound", self.DEFAULT_STOP_SOUND)
        
        self.start_audio = QSoundEffect()
        self.start_audio.setSource(QUrl.fromLocalFile(start_path))

        self.stop_audio = QSoundEffect()
        self.stop_audio.setSource(QUrl.fromLocalFile(stop_path))
        
        self.filter_name = ""
        self.filter_category = ""
        self.filter_group = ""

        # Title Bar
        self.setTitleBar(CustomTitleBar(self, ICONS_DIR))
        self.setContentsMargins(0, self.titleBar.height(), 0, 0)
        self.titleBar.raise_()
        self.titleBar.new_session_button.clicked.connect(self.on_new_session_clicked)
        self.titleBar.settings_button.clicked.connect(self.on_settings_clicked)
        self.titleBar.sidebar_button.clicked.connect(self._toggle_sidebar)
        self._sidebar_width = 260  # last known open width

        # Splitter Layout
        self.splitter = GripSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.elapse_s = 0

        sessions = self.storage.get_all_sessions()
        group_categories = self.storage.get_group_categories() # Get all group categories
        self.sidebar = Sidebar(sessions, self.on_session_selected, group_categories, ICONS_DIR)
        self.sidebar.new_session_clicked.connect(self.on_new_session_clicked)
        self.sidebar.settings_clicked.connect(self.on_settings_clicked)
        self.splitter.addWidget(self.sidebar)
        # Keep the sidebar in a sane width range so toggling panels can't make the
        # splitter blow it up or collapse it to a sliver.
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(380)
        # Prevent drag-collapsing to 0 — once at 0 there's no handle to grab.
        # Programmatic toggle uses setVisible instead, which always restores properly.
        self.splitter.setCollapsible(0, False)
        
        self.sidebar.search_changed.connect(self.on_search_changed)
        self.sidebar.category_filter_changed.connect(self.on_category_filter_changed)
        self.sidebar.group_filter_changed.connect(self.on_group_filter_changed)

        # New Session Panel
        self.new_session_panel = NewSessionPanel(self.storage.get_group_categories())
        self.new_session_panel.create_clicked.connect(
            lambda session_name, session_category, group_category: self.on_new_session_create(session_name, session_category, group_category)
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
        
        self.splitter.addWidget(self.settings_panel)
        self.settings_panel.setVisible(False)
        
        # Transcript Panel
        self.transcript_panel = TranscriptPanel(self.storage.base_dir, ICONS_DIR)
        self.transcript_panel.properties_clicked.connect(self.on_properties_clicked)
        self.transcript_panel.record_clicked.connect(self.on_record_clicked)
        self.transcript_panel.stop_recording_clicked.connect(self.on_stop_recording_confirmation)
        self.transcript_panel.force_capture_clicked.connect(self.on_force_capture_clicked)
        self.transcript_panel.summary_panel.summarize_clicked.connect(self.on_summarize_clicked)
        self.transcript_panel.capture_deleted.connect(self.storage.delete_capture)

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
        self.transcript_panel.summary_panel.summary_text_changed.connect(lambda text: self.on_text_changed(self.current_session.id, text, 3))

        self.splitter.addWidget(self.transcript_panel)
        
        # Properties Panel (created once with a placeholder session)
        self.properties_panel = None 
        
        # Recording Panel
        self.recording_panel = RecordingPanel(ICONS_DIR)
        self.recording_panel.cancel_clicked.connect(self.on_record_cancelled)
        self.recording_panel.record_clicked.connect(lambda data: self.on_recording_confirmed(data))
        
        self.splitter.addWidget(self.recording_panel)  # add this
        self.recording_panel.setVisible(False)         
        
        # Wait until the other widgets are added
        self.splitter.setSizes([260, 400, 400, 400, 400, 400]) # 1 : 4 ratio
        # The sidebar holds its width; the content panels absorb window resizing
        # and the space freed when other panels are hidden/shown.
        self.splitter.setStretchFactor(0, 0)
        for i in range(1, self.splitter.count()):
            self.splitter.setStretchFactor(i, 1)
        self.transcript_panel.set_session_locked(True) # Locked buttons initially

        # Load API keys and processing mode from saved settings
        self._load_api_keys()
        self._load_processing_mode()
        self._refresh_engine_labels()
        
        # Shortcuts
        # Shift+4 — Toggle sidebar (always active)
        self.sidebar_shortcut = QShortcut(QKeySequence("Shift+4"), self)
        self.sidebar_shortcut.activated.connect(self._toggle_sidebar)
        self.sidebar_shortcut.setEnabled(True)

        # Ctrl+T — New Session
        self.create_session_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self.create_session_shortcut.activated.connect(self.on_new_session_clicked)
        self.create_session_shortcut.setEnabled(True)
        
        # Ctrl+S — Settings
        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.settings_shortcut.activated.connect(self.on_settings_clicked)
        self.settings_shortcut.setEnabled(True)
        
        # Ctrl+D — Properties
        self.properties_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.properties_shortcut.activated.connect(self.on_properties_clicked)
        self.properties_shortcut.setEnabled(False)
        
        # Ctrl+F — Recording panel
        self.recording_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.recording_shortcut.activated.connect(self.handle_record_shortcut)
        self.recording_shortcut.setEnabled(False)

        # Ctrl+Return — Stop recording (with confirmation), only active while recording
        self.stop_recording_shortcut = QShortcut(QKeySequence("Return"), self)
        self.stop_recording_shortcut.activated.connect(self.on_stop_recording_confirmation)
        self.stop_recording_shortcut.setEnabled(False)

        # Ctrl+Shift+Return — Force capture now, only active while recording
        self.capture_now_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.capture_now_shortcut.activated.connect(self.on_force_capture_clicked)
        self.capture_now_shortcut.setEnabled(False)

    def handle_record_shortcut(self) -> None:
        # Used by Ctrl + F
        if self.is_recording_open:
            self.on_record_cancelled()
        elif not self.is_recording:
            self.on_record_clicked()

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

    def on_new_session_clicked(self) -> None:
        if self.is_new_session_open:
            self.new_session_panel.reset_form()
        
        self.is_new_session_open = not self.is_new_session_open
        self.is_properties_open = False # Close Properties when opening new session
        self.show_panel("new_session" if self.is_new_session_open else "transcript")
        
    def on_new_session_create(self, session_name, session_category, group_category) -> None:
        # Used data to build a new session
        current_time = datetime.now()
        
        # Create new session using gathered data
        new_session = Session(session_name, current_time, current_time, session_category, 0, None, group_category, None, None)
        self.storage.create_session(new_session)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())

        # Clear the form so the next new session starts blank.
        self.new_session_panel.reset_form()

        self.is_new_session_open = not self.is_new_session_open
        self.show_panel("transcript")
        
        self.current_session = new_session
        self.on_session_selected(self.current_session)
    
    def on_new_session_cancelled(self) -> None:
        self.is_new_session_open = False
        self.show_panel("transcript")
    
    def rebuild_properties_panel(self) -> None:
        if self.properties_panel:
            self.splitter.widget(self.splitter.indexOf(self.properties_panel)).setParent(None)
        self.properties_panel = PropertiesPanel(self.current_session, self.storage.get_group_categories())
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
        
    def start_recording(self, interval, region, monitor, device, hwnd=None) -> None:
        start_time = time.time()
        self.recording_start_time = start_time
        self._pending_speech = ""
        self._pending_capture_id = None

        # Start the timer only now — when capture actually begins — so the time
        # spent in the Mouse Select overlay isn't counted as recording time.
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
        self.ocr_worker.start()
        
        # Create audio worker thread
        self.audio_worker = AudioWorker(
            self.current_session.id, self.storage.base_dir, interval, device, start_time, self.current_session.length,
            speech_api_key=self._effective_api_key("speech"),
            speech_model=str(self.settings.value("speech_model", DEFAULT_SPEECH_MODEL)),
        )
        self.audio_worker.chunk_ready.connect(self.on_chunk_ready)
        self.audio_worker.chunk_pending.connect(self.on_chunk_pending)
        self.audio_worker.engine_fallback.connect(self._on_speech_engine_fallback)
        self.audio_worker.start()

        # Update footer to show live engine names
        self.transcript_panel.update_engine_labels(
            self.ocr_worker.engine_name,
            self._speech_engine_label(),
            self._summarize_engine_label(),
        )

        # Que sound effect
        self.start_audio.play()
        
        # Enable recording-only shortcuts, disable the rest
        self.create_session_shortcut.setEnabled(False)
        self.settings_shortcut.setEnabled(False)
        self.properties_shortcut.setEnabled(False)
        self.recording_shortcut.setEnabled(False)
        self.stop_recording_shortcut.setEnabled(True)
        self.capture_now_shortcut.setEnabled(True)

    def update_timer(self) -> None:
        if self.is_recording:
            self.elapse_s += 1
            
            minutes = self.elapse_s // 60
            seconds = self.elapse_s % 60
            self.transcript_panel.recording_time_label.setText(f"{minutes:02}:{seconds:02}")

    def on_record_aborted(self) -> None:
        self.is_recording = False
        self.timer.stop()
        self.elapse_s = 0
        
        # Reset Text
        self.transcript_panel.recording_time_label.setText("00:00")
        self.transcript_panel.record_button.setText("Record")
        self.transcript_panel.set_recording_active(False)
        
        # Unlock Buttons
        self.sidebar.set_recording_locked(False)
        self.transcript_panel.set_properties_locked(False)
        self.titleBar.new_session_button.setDisabled(False)
        self.titleBar.settings_button.setDisabled(False)
        self.showNormal()

    def show_overlay(self, data) -> None:
        if data.get("hwnd"):
            self.overlay = CaptureOverlay(
                lambda x, y, w, h: (
                    self.showNormal(), 
                    self.start_recording(
                        data["interval"], {"left": x, "top": y, "width": w, "height": h}, data["monitor"], data["audio_device"], hwnd=data["hwnd"]
                    )
                ),
                self.on_record_aborted,
                hwnd=data["hwnd"]
            )
        else:
            self.overlay = CaptureOverlay(
                lambda x, y, w, h: (
                    self.showNormal(), 
                    self.start_recording(
                        data["interval"], {"left": x, "top": y, "width": w, "height": h}, data["monitor"], data["audio_device"]
                    )
                ),
                self.on_record_aborted,
                monitor_index=data["monitor"]
            )
        self.show_panel("transcript")

    def on_record_clicked(self) -> None:
        # Opens the recording panel. Does NOT stop recording — that goes through confirmation
        if not self.current_session:
            print('Need to select session first')
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
        if not self.recording_panel.validate():
            return
        
        self.is_recording = True
        self.is_recording_open = False
        self.transcript_panel.record_button.setText("Recording") # Update Label
        self.transcript_panel.set_recording_active(True)
        
        # Lock Buttons
        self.sidebar.set_recording_locked(True)
        self.transcript_panel.set_properties_locked(True)
        self.titleBar.new_session_button.setDisabled(True)
        self.titleBar.settings_button.setDisabled(True)

        
        # Start the OCR and Audio threads
        if data["capture_option"] == "Mouse Select":
            self.showMinimized()
            QTimer.singleShot(300, lambda: self.show_overlay(data))
        else:
            self.show_panel("transcript")
            self.start_recording(data["interval"], data["region"], data["monitor"], data["audio_device"], hwnd=data.get("hwnd"))

    def stop_recording(self) -> None:
        self.show_panel("transcript")
        
        # Stop Timer and reset time
        self.timer.stop() 
        self.elapse_s = 0
        
        self.is_recording = False
        self.stop_audio.play()
        
        # Update labels
        self.transcript_panel.recording_time_label.setText("00:00")
        self.transcript_panel.record_button.setText("Record")
        self.transcript_panel.set_recording_active(False)
        
        # Unlock inputs
        self.sidebar.set_recording_locked(False)
        self.transcript_panel.set_properties_locked(False)
        self.titleBar.new_session_button.setDisabled(False)
        self.titleBar.settings_button.setDisabled(False)
        
        # Stop the threads
        self.ocr_worker.stop()
        self.audio_worker.stop()
        self.ocr_worker.wait()
        self.audio_worker.wait()

        # Drain capture/speech signals queued while the workers shut down, then
        # rescue any speech that never found a slide to attach to.
        QApplication.processEvents()
        if self._pending_speech:
            orphan = OCRCapture(0.0, "", "", None, self.current_session.id, self._pending_speech)
            self.storage.create_ocr_capture(orphan)
            self.transcript_panel.ocr_panel.add_capture(orphan)
            self.transcript_panel.speech_panel.add_capture(orphan)
            self._pending_speech = ""

        # save total length
        self.current_session.length += int(time.time() - self.recording_start_time)
        self.storage.update_session(self.current_session)
        
        # Assuming that recording will always give content, enable the summarize
        has_content = self.transcript_panel.ocr_panel.has_content() or self.transcript_panel.speech_panel.has_content()
        self.transcript_panel.summary_panel.summary_button.setDisabled(not has_content)
        self.transcript_panel.summary_panel.summary.setReadOnly(not has_content)
        
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
        """The capture a speech chunk should attach to: the latest slide at or before
        the speech, or — for speech that predates every slide (e.g. narration before
        the first slide finished its OCR) — the earliest slide. Returns None only when
        no slide has been captured at all yet, in which case the speech is buffered."""
        recent = self.storage.get_latest_capture_before(self.current_session.id, timestamp)
        return recent or self.storage.get_earliest_capture(self.current_session.id)

    def on_chunk_pending(self, timestamp) -> None:
        # A chunk is being transcribed; show the placeholder on the slide it will
        # attach to, if one exists yet.
        if not self.current_session:
            return
        target = self._resolve_speech_target(timestamp)
        if target:
            self._pending_capture_id = target.id
            self.transcript_panel.speech_panel.show_pending(target.id)

    def on_chunk_ready(self, timestamp, text) -> None:
        if not self.current_session:
            return
        # Clear the placeholder we actually showed (the target can drift between
        # pending and ready, so clear by the recorded id, not a fresh lookup).
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
            # No slide captured yet — hold the speech and flush it onto the first
            # capture (see on_capture_ready) so early narration isn't lost.
            self._pending_speech += text

    def on_lookup_requested(self, text: str, kind: str, target: str) -> None:
        """Translate or define a selection (right-clicked in any panel) via Gemini."""
        text = (text or "").strip()
        if not text:
            return
        # Lookups are Gemini-only; enabled whenever a key exists, regardless of the
        # Local/API processing toggle (it's an on-demand tool, not part of the pipeline).
        if not self.api_key:
            QMessageBox.information(
                self, "Gemini API key needed",
                "Add a Gemini API key in Settings to use Translate / Define."
            )
            return
        if kind == "translate" and not target:  # "Other…" — ask for a language
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
        # Don't summarize mid-recording: the transcript is still growing, and it keeps
        # summarizing and recording mutually exclusive so their locks never overlap.
        if self.is_recording:
            return
        # Ignore re-clicks while a summary is already being generated.
        if self._summarize_worker is not None:
            return

        captures = self.storage.get_captures_by_session(self.current_session.id)
        total_text = ""

        # Combine all the texts together
        for capture in captures:
            total_text += (capture.extracted_text or "") + (capture.speech_text or "")

        # Run summarization on a worker thread so the API call doesn't freeze the UI.
        # Lock the app down + show progress; results land in _on_summarize_done.
        button = self.transcript_panel.summary_panel.summary_button
        button.setDisabled(True)
        button.setText("Summarizing…")
        self._set_summarizing(True)

        self._summarize_worker = SummarizeWorker(
            total_text, api_key=self._effective_api_key("summarize")
        )
        self._summarize_worker.done.connect(self._on_summarize_done)
        self._summarize_worker.failed.connect(self._on_summarize_failed)
        self._summarize_worker.finished.connect(self._on_summarize_finished)
        self._summarize_worker.start()

    def _on_summarize_done(self, summarized_text, engine) -> None:
        self.transcript_panel.update_engine_labels(
            self.transcript_panel.ocr_engine_label.text(),
            self.transcript_panel.speech_engine_label.text(),
            engine
        )
        current = self.transcript_panel.summary_panel.current_source()

        # If the user has modified the summary, double confirm
        if current and summarized_text != current:
            reply = QMessageBox.question(
                self,
                "Summarized text modified",
                "Overwrite summarized text?"
            )
            if reply == QMessageBox.StandardButton.No:
                return
        # Ensure its not the same, to avoid updating the time period
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
        # Re-enable everything regardless of success/failure/cancel, and release the
        # worker so the next request can run.
        button = self.transcript_panel.summary_panel.summary_button
        button.setDisabled(False)
        button.setText("Summarize")
        self._set_summarizing(False)
        self._summarize_worker = None

    def _set_summarizing(self, busy: bool) -> None:
        """Lock the app down while a summary is generating so nothing can mutate the
        session underneath the worker (switching sessions mid-summary was corrupting
        state). The user can still scroll, toggle the per-capture image, and
        collapse/expand panels — nothing else. Only ever called outside recording, so
        unlocking restores the normal idle state."""
        # Sidebar: session switching, search, filters.
        self.sidebar.set_recording_locked(busy)
        # Title bar: new session + settings.
        self.titleBar.new_session_button.setDisabled(busy)
        self.titleBar.settings_button.setDisabled(busy)
        # Workspace: properties, record, sync-scroll, and both feeds (read-only + no delete).
        self.transcript_panel.set_summary_lock(busy)
        # Global shortcuts that create/open/record — save their prior state so unlocking
        # restores it exactly (some depend on whether a session is loaded).
        shortcuts = (
            self.create_session_shortcut,
            self.settings_shortcut,
            self.properties_shortcut,
            self.recording_shortcut,
        )
        if busy:
            self._locked_shortcut_states = {sc: sc.isEnabled() for sc in shortcuts}
            for sc in shortcuts:
                sc.setEnabled(False)
        else:
            for sc, was_enabled in getattr(self, "_locked_shortcut_states", {}).items():
                sc.setEnabled(was_enabled)
            self._locked_shortcut_states = {}

    def on_search_changed(self, text) -> None:
        self.filter_name = text
        self.apply_filters()

    def on_category_filter_changed(self, category) -> None:
        self.filter_category = category
        self.apply_filters()

    def on_group_filter_changed(self, group) -> None:
        self.filter_group = group
        self.apply_filters()

    def apply_filters(self) -> None:
        sessions = self.storage.search_sessions(self.filter_name, self.filter_category, self.filter_group)
        self.sidebar.refresh(sessions)
        
    def on_properties_clicked(self) -> None:
        self.is_properties_open = not self.is_properties_open
        if self.is_properties_open:
            self.rebuild_properties_panel()
        self.show_panel("properties" if self.is_properties_open else "transcript")
    
    def on_properties_cancelled(self) -> None:
        self.is_properties_open = False
        self.show_panel("transcript")

    def on_properties_saved(self, session_name, session_category, group_category) -> None:        
        # Used data to update session info
        self.current_session.name = session_name
        self.current_session.date_modified = datetime.now()
        self.current_session.session_category = session_category
        self.current_session.group_category = group_category
        self.storage.update_session(self.current_session)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())
    
    def on_properties_deleted(self) -> None:
        self.is_properties_open = not self.is_properties_open
        self.properties_panel.setVisible(self.is_properties_open)
        self.storage.delete_session(self.current_session.id)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())
        self.transcript_panel.clear_panels()
    
    def on_properties_duplicated(self) -> None:
        self.current_session = self.storage.duplicate_sessions(self.current_session.id)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())
        self.on_session_selected(self.current_session)
    
    def unsaved_changes(self) -> None:
        self.transcript_panel.saved_label.setText("Unsaved")
    
    def on_text_changed(self, id, text, option: int) -> None:
        now = datetime.now()
        self.current_session.date_modified = now
        
        # Change OCR or Speech or Summary Text 
        if option == 1:
            self.storage.update_extracted_text(id, text)
        elif option == 2:
            self.storage.update_speech_text(id, text)
        elif option == 3:
            self.current_session.summary = text

        self.storage.update_session(self.current_session)
        # Note: the sidebar/settings session lists are intentionally NOT rebuilt
        # here. Doing so on every debounced keystroke recreated every session card
        # and stuttered badly; the "modified" time refreshes on next navigation.
        self.transcript_panel.saved_label.setText("Saved")

    def on_settings_clicked(self) -> None:
        if self.is_settings_open:
            self.settings_panel.load_settings()
        
        self.is_settings_open = not self.is_settings_open
        self.is_properties_open = False # Close Properties when opening settings
        if self.is_settings_open:
            # Re-enumerate windows/devices, then restore the saved default selection.
            self.settings_panel.reload_sources()
            self.settings_panel.load_settings()
            self.settings_panel.update_ui()
        self.show_panel("settings" if self.is_settings_open else "transcript")
    
    def _load_api_keys(self) -> None:
        self.api_key = str(self.settings.value("api_key_gemini", ""))

    def _load_processing_mode(self) -> None:
        self.processing_mode = str(self.settings.value("processing_mode", "local"))

    def _effective_api_key(self, kind: str = "") -> str:
        # API is only used when the master switch is on AND that specific engine
        # (ocr / speech / summarize) is enabled for the API. This lets the user, e.g.,
        # run Gemini OCR for math slides while keeping speech on the fast local model.
        if self.processing_mode != "api":
            return ""
        if kind and not self.settings.value(f"api_use_{kind}", True, type=bool):
            return ""
        return self.api_key

    def _summarize_engine_label(self) -> str:
        return "gemini-flash" if self._effective_api_key("summarize") else "sumy"

    def _speech_engine_label(self) -> str:
        """Speech engine shown before a recording loads its model. For the local engine
        this includes the configured model (e.g. "faster-whisper · small.en"); once the
        model actually loads, engine_fallback upgrades it with the resolved model + the
        GPU/CPU device it's running on."""
        if self._effective_api_key("speech"):
            return "gemini"
        return f"faster-whisper · {self.settings.value('speech_model', DEFAULT_SPEECH_MODEL)}"

    def _refresh_engine_labels(self) -> None:
        ocr_engine = "gemini vision" if self._effective_api_key("ocr") else "pytesseract"
        # Mid-recording the worker has reported a richer label (resolved model + GPU/CPU);
        # a config-driven refresh shouldn't downgrade that to the configured value.
        if self.is_recording and not self._effective_api_key("speech"):
            speech_engine = self.transcript_panel.speech_engine_label.text()
        else:
            speech_engine = self._speech_engine_label()
        self.transcript_panel.update_engine_labels(ocr_engine, speech_engine, self._summarize_engine_label())

    def _on_ocr_engine_fallback(self, engine: str) -> None:
        self.transcript_panel.update_engine_labels(
            engine,
            self.transcript_panel.speech_engine_label.text(),
            self.transcript_panel.summarize_engine_label.text(),
        )

    def _on_speech_engine_fallback(self, engine: str) -> None:
        self.transcript_panel.update_engine_labels(
            self.transcript_panel.ocr_engine_label.text(),
            engine,
            self.transcript_panel.summarize_engine_label.text(),
        )

    def on_processing_mode_changed(self, mode: str) -> None:
        self.processing_mode = mode
        self._refresh_engine_labels()

    def on_api_keys_changed(self, key: str) -> None:
        self.api_key = key
        self._load_processing_mode()
        self._refresh_engine_labels()

    def _on_theme_changed(self, theme: str) -> None:
        refresh_icons(self, theme)
        self.sidebar.refresh_theme(theme)

    def on_sound_effects_changed(self, start: str, stop: str) -> None:
        self.start_audio.setSource(QUrl.fromLocalFile(start if start else self.DEFAULT_START_SOUND))
        self.stop_audio.setSource(QUrl.fromLocalFile(stop if stop else self.DEFAULT_STOP_SOUND))
        
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
            "session_category": session.session_category,
            "group_category": session.group_category,
            "date_recorded": session.date_recorded.isoformat(),
            "date_modified": session.date_modified.isoformat(),
            "length": session.length,
            "summary": session.summary,
            "summary_generated_at": session.summary_generated_at.isoformat() if session.summary_generated_at else None,
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
            
            # Create new session
            new_session = Session(
                name=session_data["name"],
                session_category=session_data["session_category"],
                group_category=session_data.get("group_category"),
                date_recorded=datetime.fromisoformat(session_data["date_recorded"]),
                date_modified=datetime.now(),
                length=session_data["length"],
                summary=session_data.get("summary"),
                summary_generated_at=datetime.fromisoformat(session_data["summary_generated_at"]) if session_data.get("summary_generated_at") else None,
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
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())

    def on_all_deleted_clicked(self) -> None:
        self.storage.delete_all_sessions()
        self.current_session = None
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())
        self.transcript_panel.clear_panels()

    def show_panel(self, panel: str) -> None:
        # Revert theme if leaving settings without saving
        if self.is_settings_open and panel != "settings":
            self.settings_panel.revert_theme()

        # "transcript", "settings", "new_session", "recording", "properties"
        self.transcript_panel.setVisible(panel == "transcript")
        self.settings_panel.setVisible(panel == "settings")
        self.new_session_panel.setVisible(panel == "new_session")
        self.recording_panel.setVisible(panel == "recording")

        if self.properties_panel:
            # Properties shows alongside transcript
            self.properties_panel.setVisible(panel == "properties")
            if panel == "properties":
                self.transcript_panel.setVisible(True)

        # Qt splitter sometimes leaves a newly-visible panel at 0 width if it was
        # previously "collapsed". Defer one frame to check and fix if needed.
        QTimer.singleShot(0, self._ensure_content_visible)

    def _ensure_content_visible(self) -> None:
        sizes = self.splitter.sizes()
        # Index 0 is sidebar; everything else is content. If all content panels
        # collapsed to 0, take the available space and give it to the first visible one.
        content = sizes[1:]
        if sum(content) == 0:
            available = self.splitter.width() - sizes[0]
            if available <= 0:
                return
            for i in range(1, self.splitter.count()):
                if self.splitter.widget(i).isVisible():
                    sizes[i] = available
                    self.splitter.setSizes(sizes)
                    return

    def _toggle_sidebar(self) -> None:
        if self.sidebar.isVisible():
            self._sidebar_width = self.splitter.sizes()[0]
            self.sidebar.setVisible(False)
        else:
            self.sidebar.setVisible(True)
            sizes = self.splitter.sizes()
            sizes[0] = self._sidebar_width
            self.splitter.setSizes(sizes)

    def closeEvent(self, event) -> None:
        if self._summarize_worker is not None:
            reply = QMessageBox.question(
                self,
                "Summary in progress",
                "A summary is still being generated. Closing now will cancel it. Close anyway?"
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # User chose to close mid-summary: detach the handlers so a late result
            # can't fire against torn-down widgets. The worker only emits signals (no
            # UI access), so it's safe to leave running as the process exits.
            try:
                self._summarize_worker.done.disconnect()
                self._summarize_worker.failed.disconnect()
                self._summarize_worker.finished.disconnect()
            except TypeError:
                pass
            self._summarize_worker = None

        if self.is_recording:
            reply = QMessageBox.question(
                self, 
                "Recording in progress",
                "Stop recording and close?"
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Stop the threads
                self.ocr_worker.stop()
                self.audio_worker.stop()
                self.ocr_worker.wait()
                self.audio_worker.wait()
                self.storage.close()
                event.accept()
            else:
                event.ignore()
        else:
            self.storage.close()
            event.accept()