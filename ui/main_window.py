import time
import zipfile, json

from qframelesswindow import FramelessMainWindow
from PyQt6.QtWidgets import QSplitter, QMessageBox, QFileDialog
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence, QGuiApplication
from PyQt6.QtCore import Qt, QTimer, QUrl, QSettings
from PyQt6.QtMultimedia import QSoundEffect

from pathlib import Path
from datetime import datetime

from models.lecture import Session, OCRCapture
from storage.database import Storage
from core.ocr import OCRWorker
from core.audio import AudioWorker
from core.summarizer import summarize
from ui.title_bar import CustomTitleBar
from ui.capture_overlay import CaptureOverlay
from ui.sidebar import Sidebar
from ui.new_session_panel import NewSessionPanel
from ui.transcript_panel import TranscriptPanel
from ui.properties_panel import PropertiesPanel
from ui.recording_panel import RecordingPanel
from ui.settings_panel import SettingsPanel

BASE_DIR = Path(__file__).resolve().parent
LIGHT_ICONS_DIR = BASE_DIR.parent / 'assets' / 'light_icons'
DARK_ICONS_DIR = BASE_DIR.parent / 'assets' / 'dark_icons'
ICONS_DIR = LIGHT_ICONS_DIR
APP_ICON_PATH = BASE_DIR.parent / 'assets' / 'icons' / 'LectureCapture.png'

class MainWindow(FramelessMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()
        self.settings = QSettings("LectureCapture", "LectureCapture")
        self.current_session = None
        self.is_recording = False
        self.is_new_session_open = False
        self.is_settings_open = False
        self.is_properties_open = False
        self.is_recording_open = False

        # Window details
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setWindowTitle("LectureCapture")
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)
        
        # Move it to the middle
        screen = QGuiApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())
        
        # Default Sound Effects
        self.DEFAULT_START_SOUND = str(Path(self.storage.base_dir) / 'sound_effects' / 'Beep 1 (Default).wav')
        self.DEFAULT_STOP_SOUND = str(Path(self.storage.base_dir) / 'sound_effects' / 'Chirp 1 (Default).wav')

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

        # Splitter Layout
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
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
        
        self.sidebar.search_changed.connect(self.on_search_changed)
        self.sidebar.category_filter_changed.connect(self.on_category_filter_changed)
        self.sidebar.group_filter_changed.connect(self.on_group_filter_changed)

        # New Session Panel
        self.new_session_panel = NewSessionPanel()
        self.new_session_panel.create_clicked.connect(
            lambda session_name, session_category, group_category: self.on_new_session_create(session_name, session_category, group_category)
        )
        self.new_session_panel.cancel_clicked.connect(self.on_new_session_cancelled)
        
        self.splitter.addWidget(self.new_session_panel)
        self.new_session_panel.setVisible(False)
        
        # Init the settings, and hide it
        self.settings_panel = SettingsPanel(sessions, self.storage.base_dir)
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
        self.transcript_panel.summary_panel.summarize_clicked.connect(self.on_summarize_clicked)
        
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
        self.recording_panel = RecordingPanel()
        self.recording_panel.cancel_clicked.connect(self.on_record_cancelled)
        self.recording_panel.record_clicked.connect(lambda data: self.on_recording_confirmed(data))
        
        self.splitter.addWidget(self.recording_panel)  # add this
        self.recording_panel.setVisible(False)         
        
        # Wait until the other widgets are added
        self.splitter.setSizes([100, 400, 400, 400, 400, 400]) # 1 : 4 ratio
        self.transcript_panel.set_session_locked(True) # Locked buttons initially
        
        # Shortcuts
        self.create_session_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self.create_session_shortcut.activated.connect(self.on_new_session_clicked)
        self.create_session_shortcut.setEnabled(True)
        
        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.settings_shortcut.activated.connect(self.on_settings_clicked)
        self.settings_shortcut.setEnabled(True)
        
        self.properties_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.properties_shortcut.activated.connect(self.on_properties_clicked)
        self.properties_shortcut.setEnabled(False)
        
        self.start_recording_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.start_recording_shortcut.activated.connect(self.handle_record_shortcut)
        self.start_recording_shortcut.setEnabled(False)
        
        self.end_recording_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.end_recording_shortcut.activated.connect(self.on_record_clicked)
        self.end_recording_shortcut.setEnabled(False)

    def handle_record_shortcut(self):
        if not self.is_recording_open:
            self.on_record_clicked()
        else:
            self.on_record_cancelled()

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
        self.properties_panel = PropertiesPanel(self.current_session)
        self.properties_panel.delete_clicked.connect(self.on_properties_deleted)
        self.properties_panel.duplicate_clicked.connect(self.on_properties_duplicated)
        self.properties_panel.saved_clicked.connect(
            lambda n, c, g: self.on_properties_saved(n, c, g)
        )
        self.properties_panel.cancel_clicked.connect(self.on_properties_cancelled)
        self.splitter.addWidget(self.properties_panel)
    
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
        self.start_recording_shortcut.setEnabled(True)
        
    def start_recording(self, interval, region, monitor, device, hwnd=None) -> None:
        start_time = time.time()
        self.recording_start_time = start_time
        
        # Create ocr worker thread
        self.ocr_worker = OCRWorker(
            self.current_session.id, self.storage.base_dir, interval, region, monitor, start_time, self.current_session.length, hwnd=hwnd
        )
        self.ocr_worker.capture_ready.connect(self.on_capture_ready)
        self.ocr_worker.start()
        
        # Create audio worker thread
        self.audio_worker = AudioWorker(self.current_session.id, self.storage.base_dir, interval, device, start_time, self.current_session.length)
        self.audio_worker.chunk_ready.connect(self.on_chunk_ready)
        self.audio_worker.start()

        # Que sound effect
        self.start_audio.play()
        
        # Shortcut
        self.create_session_shortcut.setEnabled(False)
        self.settings_shortcut.setEnabled(False)
        self.properties_shortcut.setEnabled(False)
        self.start_recording_shortcut.setEnabled(False)
        self.end_recording_shortcut.setEnabled(True)

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
        if not self.current_session:
            print('Need to select session first')
            return
        if not self.is_recording:
            self.show_panel("recording")
            self.is_recording_open = True
            
            # Reset the values
            self.recording_panel.reload_state()
            self.recording_panel.load_preferences()
            self.is_properties_open = False # Close Properties when opening recording
        else:
            self.stop_recording()

    def on_recording_confirmed(self, data) -> None:
        if not self.recording_panel.validate():
            return
        
        self.timer.start(1000) # Start Timer
        
        self.is_recording = True
        self.is_recording_open = False
        self.transcript_panel.record_button.setText("Stop Recording") # Update Label
        
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
        self.start_recording_shortcut.setEnabled(True)
        self.end_recording_shortcut.setEnabled(False)
        
    def on_record_cancelled(self) -> None:
        self.show_panel("transcript")
        self.is_recording_open = False
    
    def on_capture_ready(self, capture: OCRCapture) -> None:
        self.storage.create_ocr_capture(capture)
        self.transcript_panel.ocr_panel.add_capture(capture)
        self.transcript_panel.speech_panel.add_capture(capture)

    def on_chunk_ready(self, timestamp, text) -> None:
        captures = self.storage.get_captures_by_session(self.current_session.id)
        recent = None
        for capture in captures:
            if capture.timestamp <= timestamp:
                recent = capture
            else:
                break
        
        if recent:
            self.storage.append_speech_text(recent.id, text)
            self.transcript_panel.speech_panel.update_capture_speech(recent.id, text)
    
    def on_summarize_clicked(self) -> None:
        if not self.current_session:
            print('Need to select session first')
            return
        
        captures = self.storage.get_captures_by_session(self.current_session.id)
        total_text = ""
        
        # Combine all the texts together
        for capture in captures:
            total_text += (capture.extracted_text or "") + (capture.speech_text or "")
        
        # Summarize then update the QTextEdit and current_session object
        summarized_text = summarize(total_text)
        current = self.transcript_panel.summary_panel.summary.toPlainText()
        
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
        
        # Assign while blocking the signal to avoid triggering on_text_changed
        summary_widget = self.transcript_panel.summary_panel.summary
        summary_widget.blockSignals(True)
        summary_widget.setText(summarized_text)
        summary_widget.blockSignals(False)
        
        self.current_session.summary = summarized_text
        current_time = datetime.now()
        self.current_session.summary_generated_at = current_time
        self.current_session.date_modified = current_time
        self.storage.update_session(self.current_session)
        
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
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.settings_panel.refresh_sessions(self.storage.get_all_sessions())
        self.transcript_panel.saved_label.setText("Saved")

    def on_settings_clicked(self) -> None:
        if self.is_settings_open:
            self.settings_panel.load_settings()
        
        self.is_settings_open = not self.is_settings_open
        self.is_properties_open = False # Close Properties when opening settings
        self.show_panel("settings" if self.is_settings_open else "transcript")
    
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

    def closeEvent(self, event) -> None:
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
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()