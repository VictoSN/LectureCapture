from PyQt6.QtWidgets import (
    QWidget, QLabel, QSplitter, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

from models.lecture import Session, OCRCapture
from ui.styles import create_label, create_button
from ui.ocr_panel import OCRPanel
from ui.speech_panel import SpeechPanel
from ui.summary_panel import SummaryPanel

class TranscriptPanel(QWidget):
    properties_clicked = pyqtSignal()
    record_clicked = pyqtSignal()          # open recording panel
    stop_recording_clicked = pyqtSignal()  # request stop (with confirmation) while recording
    force_capture_clicked = pyqtSignal()
    capture_deleted = pyqtSignal(int)
    
    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        footer = QHBoxLayout()
        self.base_dir = base_dir

        self._sync_scroll_enabled = False
        self._sync_connection_ocr = None
        self._sync_connection_speech = None

        # Header Layout
        self.session_name = QLabel()
        self.session_name.setText("Select a session")
        header.addWidget(self.session_name)

        self.properties_button = create_button(icons_dir / 'info.svg', self.properties_clicked, text="Properties", width=110)
        header.addWidget(self.properties_button)

        self.sync_scroll_button = create_button(icons_dir / 'lock.svg', self._toggle_sync_scroll, text="Scroll Lock", width=110)
        header.addWidget(self.sync_scroll_button)

        self.ocr_visibility_button = create_button(icons_dir / 'scan.svg', lambda: self._panel_visibility(self.ocr_panel), text="OCR", width=80)
        header.addWidget(self.ocr_visibility_button)

        self.speech_visibility_button = create_button(icons_dir / 'microphone.svg', lambda: self._panel_visibility(self.speech_panel), text="Audio", width=80)
        header.addWidget(self.speech_visibility_button)

        self.summary_visibility_button = create_button(icons_dir / 'summarize.svg', lambda: self._panel_visibility(self.summary_panel), text="Summary", width=110)
        header.addWidget(self.summary_visibility_button)

        self.force_capture_button = create_button(icons_dir / 'scan.svg', self.force_capture_clicked, text="Capture Now", width=120)
        self.force_capture_button.setVisible(False)
        header.addWidget(self.force_capture_button)

        self.record_button = create_button(icons_dir / 'red_dot.svg', self._on_record_button_clicked, text="Record", width=120)
        header.addWidget(self.record_button)

        # Splitter Layout for content
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.ocr_panel = OCRPanel(base_dir, icons_dir)
        self.speech_panel = SpeechPanel(base_dir, icons_dir)
        self.summary_panel = SummaryPanel(icons_dir)

        self.splitter.addWidget(self.ocr_panel)
        self.splitter.addWidget(self.speech_panel)
        self.splitter.addWidget(self.summary_panel)
        self.splitter.setSizes([100, 100, 100]) # 1 : 4 ratio

        # Sync row heights whenever a new capture is added during recording.
        # Defer via singleShot(0) so Qt finishes laying out the new widgets first.
        self.ocr_panel.capture_added.connect(
            lambda: QTimer.singleShot(0, self._sync_row_heights)
        )

        # When either panel deletes a capture, remove the matching row from the
        # other panel and bubble the signal up so the controller can hit the DB.
        self.ocr_panel.capture_deleted.connect(self._on_capture_deleted)
        self.speech_panel.capture_deleted.connect(self._on_capture_deleted)

        # Info Footer
        clock_w, self.recording_time_label = create_label(icons_dir / 'clock.svg', '00:00')
        saved_w, self.saved_label = create_label(icons_dir / 'save.svg', 'Saved')
        ocr_w, self.ocr_engine_label = create_label(icons_dir / 'scan.svg', 'pytesseract')
        speech_w, self.speech_engine_label = create_label(icons_dir / 'microphone.svg', 'faster-whisper')
        summary_w, self.summarize_engine_label = create_label(icons_dir / 'summarize.svg', 'sumy')

        for w in [clock_w, saved_w, ocr_w, speech_w, summary_w]:
            footer.addWidget(w)

        footer.setSpacing(14)
        footer.setAlignment(Qt.AlignmentFlag.AlignLeft)

        main_layout.addLayout(header)
        main_layout.addWidget(self.splitter)
        main_layout.addLayout(footer)
        self.setLayout(main_layout)
        
        # Shortcuts
        self.ocr_shortcut = QShortcut(QKeySequence("Shift+1"), self)
        self.ocr_shortcut.activated.connect(lambda: self._panel_visibility(self.ocr_panel))
        self.ocr_shortcut.setEnabled(True)
        
        self.speech_shortcut = QShortcut(QKeySequence("Shift+2"), self)
        self.speech_shortcut.activated.connect(lambda: self._panel_visibility(self.speech_panel))
        self.speech_shortcut.setEnabled(True)
        
        self.summary_shortcut = QShortcut(QKeySequence("Shift+3"), self)
        self.summary_shortcut.activated.connect(lambda: self._panel_visibility(self.summary_panel))
        self.summary_shortcut.setEnabled(True)

        self._toggle_sync_scroll()

    def _on_record_button_clicked(self) -> None:
        if self.record_button.text() == "Recording":
            self.stop_recording_clicked.emit()
        else:
            self.record_clicked.emit()

    def set_recording_active(self, active: bool) -> None:
        """Show/hide the force capture button based on recording state."""
        self.force_capture_button.setVisible(active)

    def _on_capture_deleted(self, capture_id: int) -> None:
        """Remove the matching row from both panels and notify the controller."""
        for panel in (self.ocr_panel, self.speech_panel):
            for i in range(panel.feed_layout.count()):
                w = panel.feed_layout.itemAt(i).widget()
                if w and w.property("capture_id") == capture_id:
                    panel.feed_layout.removeWidget(w)
                    w.deleteLater()
                    break
        self.capture_deleted.emit(capture_id)

    def _sync_row_heights(self):
        ocr_count = self.ocr_panel.feed_layout.count()
        speech_count = self.speech_panel.feed_layout.count()
        count = min(ocr_count, speech_count)

        for i in range(count):
            ocr_w = self.ocr_panel.feed_layout.itemAt(i).widget()
            speech_w = self.speech_panel.feed_layout.itemAt(i).widget()
            if ocr_w and speech_w:
                # sizeHint is unreliable for freshly added widgets that haven't
                # been painted yet (often returns 0 or a tiny value).  Take the
                # larger of the two actual heights (already-set fixedHeight or
                # the geometry height) so we never shrink a row that was already
                # sized correctly.
                current_h = max(ocr_w.height(), speech_w.height())
                hint_h = max(ocr_w.sizeHint().height(), speech_w.sizeHint().height())
                h = max(current_h, hint_h, 300)
                ocr_w.setFixedHeight(h)
                speech_w.setFixedHeight(h)

    def _toggle_sync_scroll(self):
        self._sync_scroll_enabled = not self._sync_scroll_enabled

        ocr_bar = self.ocr_panel.scroll.verticalScrollBar()
        speech_bar = self.speech_panel.scroll.verticalScrollBar()

        if self._sync_scroll_enabled:
            self._sync_connection_ocr = ocr_bar.valueChanged.connect(speech_bar.setValue)
            self._sync_connection_speech = speech_bar.valueChanged.connect(ocr_bar.setValue)
        else:
            ocr_bar.valueChanged.disconnect(speech_bar.setValue)
            speech_bar.valueChanged.disconnect(ocr_bar.setValue)

    def _panel_visibility(self, panel: QWidget):
        panel.setVisible(not panel.isVisible())
        self._rebalance_splitter()

    def _rebalance_splitter(self):
        panels = [self.ocr_panel, self.speech_panel, self.summary_panel]
        visible = [p for p in panels if p.isVisible()]

        if not visible:
            return

        total = self.splitter.width()
        share = total // len(visible)

        sizes = []
        for p in panels:
            sizes.append(share if p.isVisible() else 0)

        self.splitter.setSizes(sizes)

    def on_recording_stopped(self) -> None:
        """Call this when recording ends to ensure all row heights are correct."""
        QTimer.singleShot(0, self._sync_row_heights)

    def load_session(self, session: Session, captures: OCRCapture) -> None:
        self.set_session_locked(False)
        self.session_name.setText(session.name)
        
        self.ocr_panel.load_captures(captures)
        self.speech_panel.load_captures(captures)
        self._sync_row_heights()
        
        #  Lock summary button if no content is available
        has_content = self.ocr_panel.has_content() or self.speech_panel.has_content()
        self.summary_panel.summary_button.setDisabled(not has_content)
        self.summary_panel.summary.setReadOnly(not has_content)
        
        if session.summary:
            # Assign the summary text, while blocking signal to prevent triggering on_text_changed
            summary_widget = self.summary_panel.summary
            summary_widget.blockSignals(True)
            summary_widget.setPlainText(session.summary)
            summary_widget.blockSignals(False)
        else:
            self.summary_panel.summary.clear()
            self.summary_panel.summary.setPlaceholderText('Press "Summarize" to generate a summary.')
            
    def set_session_locked(self, locked: bool) -> None:
        self.properties_button.setDisabled(locked)
        self.sync_scroll_button.setDisabled(locked)
        
        self.ocr_visibility_button.setDisabled(locked)
        self.speech_visibility_button.setDisabled(locked)
        self.summary_visibility_button.setDisabled(locked)
        self.record_button.setDisabled(locked)
        
        self.ocr_panel.ocr_button.setDisabled(locked)
        self.speech_panel.speech_button.setDisabled(locked)
        self.summary_panel.summary_button.setDisabled(locked)

        self.ocr_shortcut.setEnabled(not locked)
        self.speech_shortcut.setEnabled(not locked)
        self.summary_shortcut.setEnabled(not locked)

    def set_properties_locked(self, locked: bool) -> None:
        self.properties_button.setDisabled(locked)
    
    def clear_panels(self) -> None:
        self.set_session_locked(True)
        self.ocr_panel.clear_captures()
        self.speech_panel.clear_captures()
        self.summary_panel.summary.clear()

    def update_engine_labels(self, ocr_engine: str, speech_engine: str, summarize_engine: str) -> None:
        self.ocr_engine_label.setText(ocr_engine)
        self.speech_engine_label.setText(speech_engine)
        self.summarize_engine_label.setText(summarize_engine)