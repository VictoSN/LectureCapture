import time

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer

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

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR.parent / 'assets' / 'icon.png'

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()
        self.current_session = None
        self.is_recording = False

        # Window details
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1100, 700)
        self.setWindowTitle("LectureCapture")

        self.filter_name = ""
        self.filter_category = ""
        self.filter_group = ""

        # Splitter Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        sessions = self.storage.get_all_sessions()
        group_categories = self.storage.get_group_categories() # Get all group categories
        self.sidebar = Sidebar(sessions, self.on_new_session, self.on_session_selected, group_categories)
        splitter.addWidget(self.sidebar)
        
        self.sidebar.search_changed.connect(self.on_search_changed)
        self.sidebar.category_filter_changed.connect(self.on_category_filter_changed)
        self.sidebar.group_filter_changed.connect(self.on_group_filter_changed)

        self.transcript_panel = TranscriptPanel(self.storage.base_dir, self.on_properties_clicked)
        self.transcript_panel.record_clicked.connect(self.on_record_clicked)
        self.transcript_panel.summary_panel.summarize_clicked.connect(self.on_summarize_clicked)
        splitter.addWidget(self.transcript_panel)

        # Wait until the other widgets are added
        splitter.setSizes([100, 400]) # 1 : 4 ratio
        self.transcript_panel.set_session_locked(True) # Locked buttons initially

    def on_new_session(self):
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
    
    def on_session_selected(self, session: Session):
        self.current_session = session
        captures = self.storage.get_captures_by_session(session.id)
        self.transcript_panel.load_session(session, captures)
        
    def start_recording(self, interval, region, monitor):
        start_time = time.time()
        self.recording_start_time = start_time
        
        # Create ocr worker thread
        self.ocr_worker = OCRWorker(self.current_session.id, self.storage.base_dir, interval, region, monitor, start_time, self.current_session.length)
        self.ocr_worker.capture_ready.connect(self.on_capture_ready)
        self.ocr_worker.start()
        
        # Create audio worker thread
        self.audio_worker = AudioWorker(self.current_session.id, self.storage.base_dir, interval, start_time, self.current_session.length)
        self.audio_worker.chunk_ready.connect(self.on_chunk_ready)
        self.audio_worker.start()
        
    def on_record_clicked(self):
        if not self.current_session:
            print('Need to select session first')
            return
        
        if not self.is_recording:            
            # Get data from dialog
            dialog = RecordingDialog()
            
            if dialog.exec():
                data = dialog.get_data()
                self.is_recording = True
                self.transcript_panel.record_button.setText("Stop Recording")
                self.sidebar.set_recording_locked(True)
                self.transcript_panel.set_properties_locked(True)

                if data["capture_option"] == "Mouse Select":
                    self.showMinimized() # Hide the program
                    self.overlay = CaptureOverlay(
                        lambda x, y, w, h: self.start_recording(data["interval"], {"left": x, "top": y, "width": w, "height": h}, data["monitor"]),
                        lambda: None  # cancel callback
                    )
                    QTimer.singleShot(200, self.showNormal) # Show the program back
                else:
                    self.start_recording(data["interval"], data["region"], data["monitor"])
        else:
            self.is_recording = False
            self.transcript_panel.record_button.setText("Record")
            self.sidebar.set_recording_locked(False)
            self.transcript_panel.set_properties_locked(False)
            self.ocr_worker.stop()
            self.audio_worker.stop()
            
            # save total length
            self.current_session.length += int(time.time() - self.recording_start_time)
            self.storage.update_session(self.current_session)
            
    def on_capture_ready(self, capture: OCRCapture):
        self.storage.create_ocr_capture(capture)
        self.transcript_panel.ocr_panel.add_capture(capture)
        self.transcript_panel.speech_panel.add_capture(capture)
        
    def on_chunk_ready(self, timestamp, text):
        captures = self.storage.get_captures_by_session(self.current_session.id)
        
        recent = None
        for capture in captures:
            if capture.timestamp <= timestamp:
                recent = capture
            else:
                break
        
        if recent:
            self.storage.update_capture_speech(recent.id, text)
            self.transcript_panel.speech_panel.update_capture_speech(recent.id, text)
    
    def on_summarize_clicked(self):
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
        self.transcript_panel.summary_panel.summary.setText(summarized_text)
        self.current_session.summary = summarized_text
        current_time = datetime.now()
        self.current_session.summary_generated_at = current_time
        self.current_session.date_modified = current_time
        self.storage.update_session(self.current_session)
        
    def on_search_changed(self, text):
        self.filter_name = text
        self.apply_filters()

    def on_category_filter_changed(self, category):
        self.filter_category = category
        self.apply_filters()

    def on_group_filter_changed(self, group):
        self.filter_group = group
        self.apply_filters()

    def apply_filters(self):
        sessions = self.storage.search_sessions(self.filter_name, self.filter_category, self.filter_group)
        self.sidebar.refresh(sessions)
        
    def on_properties_clicked(self):
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
    
    def on_deleted_clicked(self):
        self.storage.delete_session(self.current_session.id)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.transcript_panel.clear_panels()
    
    def on_duplicated_clicked(self):
        self.current_session = self.storage.duplicate_sessions(self.current_session.id)
        self.sidebar.refresh(self.storage.get_all_sessions())
        self.on_session_selected(self.current_session)