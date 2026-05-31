import time

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QMessageBox
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QSoundEffect

from models.lecture import Session, OCRCapture
from storage.database import Storage
from pathlib import Path
from datetime import datetime

from core.ocr import OCRWorker
from core.audio import AudioWorker
from core.summarizer import summarize
from ui.capture_overlay import CaptureOverlay
from ui.sidebar import Sidebar
from ui.new_session_dialog import NewSessionDialog
from ui.transcript_panel import TranscriptPanel
from ui.properties_dialog import PropertiesDialog
from ui.recording_dialog import RecordingDialog
from ui.settings_panel import SettingsPanel

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR.parent / 'assets' / 'icon.png'

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()
        self.current_session = None
        self.is_recording = False
        self.is_settings_open = False

        # Window details
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1100, 700)
        self.setWindowTitle("LectureCapture")

        # Sound Effects
        # TODO: Add option in settings panel to change the audio
        self.start_audio = QSoundEffect()
        self.start_audio.setSource(QUrl.fromLocalFile(str(BASE_DIR.parent / 'assets' / 'sound_effects' / 'Beep 1.wav')))

        self.end_audio = QSoundEffect()
        self.end_audio.setSource(QUrl.fromLocalFile(str(BASE_DIR.parent / 'assets' / 'sound_effects' / 'Chirp 1.wav')))

        self.filter_name = ""
        self.filter_category = ""
        self.filter_group = ""

        # Splitter Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.elapse_s = 0

        sessions = self.storage.get_all_sessions()
        group_categories = self.storage.get_group_categories() # Get all group categories
        self.sidebar = Sidebar(sessions, self.on_session_selected, group_categories)
        self.sidebar.new_session_clicked.connect(self.on_new_session)
        self.sidebar.settings_clicked.connect(self.on_settings_clicked)
        splitter.addWidget(self.sidebar)
        
        self.sidebar.search_changed.connect(self.on_search_changed)
        self.sidebar.category_filter_changed.connect(self.on_category_filter_changed)
        self.sidebar.group_filter_changed.connect(self.on_group_filter_changed)

        self.transcript_panel = TranscriptPanel(self.storage.base_dir)
        self.transcript_panel.properties_clicked.connect(self.on_properties_clicked)
        self.transcript_panel.record_clicked.connect(self.on_record_clicked)
        self.transcript_panel.summary_panel.summarize_clicked.connect(self.on_summarize_clicked)
        
        # Init the settings, and hide it
        self.settings_panel = SettingsPanel(self.storage.base_dir)
        splitter.addWidget(self.settings_panel)
        self.settings_panel.setVisible(False)
        
        # When any content is changed
        self.transcript_panel.ocr_panel.ocr_text_changed.connect(lambda cid, text: self.on_text_changed(cid, text, 1))
        self.transcript_panel.speech_panel.speech_text_changed.connect(lambda cid, text: self.on_text_changed(cid, text, 2))
        self.transcript_panel.summary_panel.summary_text_changed.connect(lambda text: self.on_text_changed(self.current_session.id, text, 3))
        splitter.addWidget(self.transcript_panel)

        # Wait until the other widgets are added
        splitter.setSizes([100, 400, 400]) # 1 : 4 ratio
        self.transcript_panel.set_session_locked(True) # Locked buttons initially

    def on_new_session(self) -> None:
        dialog = NewSessionDialog()
        
        # Exec blocks until dialog is closed (accepted/cancelled)
        if dialog.exec():
            # Used data to build a new session
            data = dialog.get_data() 
            current_time = datetime.now()
            print(data)
            
            # Create new session using gathered data
            new_session = Session(data["session_name"], current_time, current_time, data["session_category"], 0, None, data["group_category"], None, None)
            self.storage.create_session(new_session)
            self.sidebar.refresh(self.storage.get_all_sessions())
    
    def on_session_selected(self, session: Session) -> None:
        self.current_session = session
        captures = self.storage.get_captures_by_session(session.id)
        self.transcript_panel.load_session(session, captures)
        
        # Close the settings panel if its opened
        if self.is_settings_open:
            self.on_settings_clicked()
        
    def start_recording(self, interval, region, monitor, device) -> None:
        start_time = time.time()
        self.recording_start_time = start_time
        
        # Create ocr worker thread
        self.ocr_worker = OCRWorker(self.current_session.id, self.storage.base_dir, interval, region, monitor, start_time, self.current_session.length)
        self.ocr_worker.capture_ready.connect(self.on_capture_ready)
        self.ocr_worker.start()
        
        # Create audio worker thread
        self.audio_worker = AudioWorker(self.current_session.id, self.storage.base_dir, interval, device, start_time, self.current_session.length)
        self.audio_worker.chunk_ready.connect(self.on_chunk_ready)
        self.audio_worker.start()

        # Que sound effect
        self.start_audio.play()
        
    def update_timer(self) -> None:
        if self.is_recording:
            self.elapse_s += 1
            
            minutes = self.elapse_s // 60
            seconds = self.elapse_s % 60
            self.transcript_panel.recording_time_label.setText(f"{minutes:02}:{seconds:02}")

    def on_record_cancelled(self) -> None:
        self.is_recording = False
        self.timer.stop()
        self.elapse_s = 0
        self.transcript_panel.recording_time_label.setText("00:00")
        self.transcript_panel.record_button.setText("Record")
        self.sidebar.set_recording_locked(False)
        self.transcript_panel.set_properties_locked(False)

    def on_record_clicked(self) -> None:
        if not self.current_session:
            print('Need to select session first')
            return
        
        if not self.is_recording:            
            # Get data from dialog
            dialog = RecordingDialog()
            
            if dialog.exec():
                data = dialog.get_data()
                self.timer.start(1000) # Start Timer
                
                self.is_recording = True
                
                # Update Label
                self.transcript_panel.record_button.setText("Stop Recording")
                
                # Lock inputs
                self.sidebar.set_recording_locked(True)
                self.transcript_panel.set_properties_locked(True)

                # Start the OCR and Audio threads
                if data["capture_option"] == "Mouse Select":
                    self.showMinimized() # Hide the program
                    self.overlay = CaptureOverlay(
                        lambda x, y, w, h: self.start_recording(data["interval"], {"left": x, "top": y, "width": w, "height": h}, data["monitor"], data["audio_device"]),
                        self.on_record_cancelled, # cancel callback
                        data["monitor"]
                    )
                    QTimer.singleShot(500, self.showNormal) # Show the program back
                else:
                    self.start_recording(data["interval"], data["region"], data["monitor"], data["audio_device"])
        else:
            # Stop Timer and reset time
            self.timer.stop() 
            self.elapse_s = 0
            
            self.is_recording = False
            self.end_audio.play()
            
            # Update labels
            self.transcript_panel.recording_time_label.setText("00:00")
            self.transcript_panel.record_button.setText("Record")
            
            # Unlock inputs
            self.sidebar.set_recording_locked(False)
            self.transcript_panel.set_properties_locked(False)
            
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
        dialog = PropertiesDialog(self.current_session)
        dialog.delete_clicked.connect(self.on_deleted_clicked)
        dialog.duplicate_clicked.connect(self.on_duplicated_clicked)
        
        # Exec blocks until dialog is closed (accepted/cancelled)
        if dialog.exec():
            # Used data to update session info
            data = dialog.get_data() 
            print(data)
            self.current_session.name = data["name"]
            self.current_session.date_modified = datetime.now()
            self.current_session.session_category = data["session_category"]
            self.current_session.group_category = data["group_category"]
            self.storage.update_session(self.current_session)
            self.sidebar.refresh(self.storage.get_all_sessions())
    
    def on_deleted_clicked(self) -> None:
        self.storage.delete_session(self.current_session.id)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.transcript_panel.clear_panels()
    
    def on_duplicated_clicked(self) -> None:
        self.current_session = self.storage.duplicate_sessions(self.current_session.id)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.on_session_selected(self.current_session)
    
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

    def on_settings_clicked(self) -> None:
        self.is_settings_open = not self.is_settings_open
        
        # Only show either the transcript or settings panel
        self.transcript_panel.setVisible(not self.is_settings_open)
        self.settings_panel.setVisible(self.is_settings_open)

    def closeEvent(self, event) -> None:
        if self.is_recording:
            reply = QMessageBox.question(self, "Recording in progress",
                                "Stop recording and close?")
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