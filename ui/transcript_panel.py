from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QSizePolicy
)
from ui.grip_splitter import GripSplitter
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

from models.lecture import Session, OCRCapture
from ui.styles import create_label, create_button, load_icon
from ui.ocr_panel import OCRPanel
from ui.speech_panel import SpeechPanel
from ui.summary_panel import SummaryPanel

class TranscriptPanel(QWidget):
    properties_clicked = pyqtSignal()
    record_clicked = pyqtSignal()          # open recording panel
    stop_recording_clicked = pyqtSignal()  # request stop (with confirmation) while recording
    force_capture_clicked = pyqtSignal()
    capture_deleted = pyqtSignal(int)
    quiz_clicked = pyqtSignal()            # open the quiz workspace
    
    def __init__(self, base_dir, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(14, 12, 14, 10)
        main_layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(8)
        footer = QHBoxLayout()
        self.base_dir = base_dir
        self._icons_dir = icons_dir

        self._sync_scroll_enabled = False
        self._sync_connection_ocr = None
        self._sync_connection_speech = None

        # Header Layout — label with a border-bottom separator for the underline effect
        self.session_name = QLabel()
        self.session_name.setText("Select a session")
        self.session_name.setStyleSheet("font-weight: 600;")
        self._name_sep = QFrame()
        self._name_sep.setFrameShape(QFrame.Shape.HLine)
        self._name_sep.setObjectName("sessionNameSep")
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_col.setContentsMargins(0, 0, 12, 0)
        name_col.addWidget(self.session_name)
        name_col.addWidget(self._name_sep)
        header.addLayout(name_col)

        self.properties_button = create_button(icons_dir / 'info.svg', self.properties_clicked, text="Properties", width=110)
        self.properties_button.setToolTip("Session properties (Ctrl+D)")
        header.addWidget(self.properties_button)

        self.sync_scroll_button = create_button(icons_dir / 'unlock.svg', self._toggle_sync_scroll, text="Scroll Unsync", width=126)
        self.sync_scroll_button.setToolTip("Sync OCR and Audio scroll positions")
        header.addWidget(self.sync_scroll_button)

        self.ocr_visibility_button = create_button(icons_dir / 'scan.svg', lambda: self._panel_visibility(self.ocr_panel), text="OCR", width=80)
        self.ocr_visibility_button.setToolTip("Toggle OCR panel (Shift+1)")
        header.addWidget(self.ocr_visibility_button)

        self.speech_visibility_button = create_button(icons_dir / 'microphone.svg', lambda: self._panel_visibility(self.speech_panel), text="Audio", width=80)
        self.speech_visibility_button.setToolTip("Toggle Audio panel (Shift+2)")
        header.addWidget(self.speech_visibility_button)

        self.summary_visibility_button = create_button(icons_dir / 'summarize.svg', lambda: self._panel_visibility(self.summary_panel), text="Summary", width=110)
        self.summary_visibility_button.setToolTip("Toggle Summary panel (Shift+3)")
        header.addWidget(self.summary_visibility_button)

        self.quiz_button = create_button(icons_dir / 'question.svg', self.quiz_clicked, text="Quiz", width=90)
        self.quiz_button.setToolTip("Generate a quiz from this session")
        header.addWidget(self.quiz_button)

        # These are toggles driven by click or Shift+1/2/3, so they don't need to keep
        # keyboard focus — and the focus border (coral) would otherwise look identical
        # to the "panel open" highlight, hiding the open/closed state.
        for _b in (self.ocr_visibility_button, self.speech_visibility_button, self.summary_visibility_button):
            _b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.force_capture_button = create_button(icons_dir / 'scan.svg', self.force_capture_clicked, text="Capture Now", width=132)
        self.force_capture_button.setToolTip("Force a capture now (Ctrl+Return)")
        self.force_capture_button.setVisible(False)
        header.addWidget(self.force_capture_button)

        self.record_button = create_button(icons_dir / 'red_dot.svg', self._on_record_button_clicked, text="Record", width=120)
        self.record_button.setToolTip("Open recording panel (Ctrl+F)")
        header.addWidget(self.record_button)

        # Splitter Layout for content
        self.splitter = GripSplitter(Qt.Orientation.Horizontal)
        self.ocr_panel = OCRPanel(base_dir, icons_dir)
        self.speech_panel = SpeechPanel(base_dir, icons_dir)
        self.summary_panel = SummaryPanel(icons_dir)

        self.splitter.addWidget(self.ocr_panel)
        self.splitter.addWidget(self.speech_panel)
        self.splitter.addWidget(self.summary_panel)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 1)
        # setSizes before the widget is shown has no effect (width=0).
        # Defer so the splitter has its real pixel width on the first frame.
        QTimer.singleShot(0, self._rebalance_splitter)

        # Sync row heights whenever a new capture is added during recording.
        # Defer via singleShot(0) so Qt finishes laying out the new widgets first.
        self.ocr_panel.capture_added.connect(
            lambda: QTimer.singleShot(0, self._sync_row_heights)
        )

        # Re-sync row heights after the user finishes resizing the window or
        # dragging a splitter handle. Debounced so a burst of resize events
        # collapses into a single recompute, and allowed to shrink so rows track
        # the panel's new width in both directions.
        self._resync_timer = QTimer(self)
        self._resync_timer.setSingleShot(True)
        self._resync_timer.setInterval(120)
        self._resync_timer.timeout.connect(lambda: self._sync_row_heights(allow_shrink=True))
        self.splitter.splitterMoved.connect(lambda *_: self._resync_timer.start())

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

        # Connection warning — a full-width red bar just above the engine labels, shown
        # when an API call fails / there's no key during recording. Fixed height so it
        # stays a thin horizontal strip; hidden (taking no space) the rest of the time.
        self._banner_dismissed = False
        self.connection_banner = QFrame()
        self.connection_banner.setObjectName("connectionBanner")
        self.connection_banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.connection_banner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.connection_banner.setVisible(False)
        banner_layout = QHBoxLayout(self.connection_banner)
        banner_layout.setContentsMargins(12, 4, 8, 4)
        banner_layout.setSpacing(8)
        self._connection_label = QLabel("")
        self._connection_label.setObjectName("connectionBannerText")
        banner_layout.addWidget(self._connection_label)
        banner_layout.addStretch()
        self._connection_close = QPushButton("✕")
        self._connection_close.setObjectName("connectionBannerClose")
        self._connection_close.setFixedSize(22, 22)
        self._connection_close.setToolTip("Dismiss")
        self._connection_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connection_close.clicked.connect(self._dismiss_connection_warning)
        banner_layout.addWidget(self._connection_close)

        main_layout.addLayout(header)
        main_layout.addWidget(self.splitter)
        main_layout.addWidget(self.connection_banner)
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
        self._refresh_panel_buttons()  # reflect the initial (all-open) panel state

    def _on_record_button_clicked(self) -> None:
        if self.record_button.text() == "Recording":
            self.stop_recording_clicked.emit()
        else:
            self.record_clicked.emit()

    def set_recording_active(self, active: bool) -> None:
        """Show/hide the force capture button based on recording state."""
        self.force_capture_button.setVisible(active)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Panel widths just changed -> the aspect-ratio images (and therefore the
        # ideal row heights) changed too. Debounce so we recompute once the
        # resize/drag settles rather than on every intermediate event.
        self._resync_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # A child's isVisible() only reads true once this panel is itself shown, so
        # refresh the toggle highlights after the show propagates (one frame later).
        QTimer.singleShot(0, self._refresh_panel_buttons)

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

    def _sync_row_heights(self, allow_shrink: bool = False):
        # allow_shrink=False (the default, used right after a capture is added):
        #   never shorten a row -- a freshly added widget's sizeHint is unreliable
        #   before it is painted, so we keep whatever height it already has.
        # allow_shrink=True (used after a resize settles): size purely from the
        #   now-reliable sizeHints so rows track the panel's new width downward
        #   too, instead of ratcheting only upward.
        ocr_count = self.ocr_panel.feed_layout.count()
        speech_count = self.speech_panel.feed_layout.count()
        count = min(ocr_count, speech_count)

        for i in range(count):
            ocr_w = self.ocr_panel.feed_layout.itemAt(i).widget()
            speech_w = self.speech_panel.feed_layout.itemAt(i).widget()
            if ocr_w and speech_w:
                hint_h = max(ocr_w.sizeHint().height(), speech_w.sizeHint().height())
                if allow_shrink:
                    h = max(hint_h, 300)
                else:
                    current_h = max(ocr_w.height(), speech_w.height())
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
            self.sync_scroll_button.setText("Scroll Sync")
            self.sync_scroll_button.setIcon(load_icon(self._icons_dir / 'lock.svg'))
        else:
            ocr_bar.valueChanged.disconnect(speech_bar.setValue)
            speech_bar.valueChanged.disconnect(ocr_bar.setValue)
            self.sync_scroll_button.setText("Scroll Unsync")
            self.sync_scroll_button.setIcon(load_icon(self._icons_dir / 'unlock.svg'))

    def _panel_visibility(self, panel: QWidget):
        panel.setVisible(not panel.isVisible())
        self._rebalance_splitter()
        self._refresh_panel_buttons()

    def _refresh_panel_buttons(self) -> None:
        # Reflect each panel's open/closed state on its toggle button: the QSS lights
        # the button (coral) when the panel is shown and mutes it when hidden, so the
        # button itself tells you what's collapsed. Repolish so the change applies now.
        for btn, panel in (
            (self.ocr_visibility_button, self.ocr_panel),
            (self.speech_visibility_button, self.speech_panel),
            (self.summary_visibility_button, self.summary_panel),
        ):
            btn.setProperty("panelOpen", panel.isVisible())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _rebalance_splitter(self):
        panels = [self.ocr_panel, self.speech_panel, self.summary_panel]
        weights = [2, 2, 1]
        visible = [(p, w) for p, w in zip(panels, weights) if p.isVisible()]

        if not visible:
            return

        total = self.splitter.width()
        total_weight = sum(w for _, w in visible)

        sizes = []
        for p, w in zip(panels, weights):
            sizes.append(int(total * w / total_weight) if p.isVisible() else 0)

        self.splitter.setSizes(sizes)
        # setSizes() doesn't emit splitterMoved, so resync row heights to the new
        # panel widths ourselves once the relayout settles.
        self._resync_timer.start()

    def on_recording_stopped(self) -> None:
        """Call this when recording ends to ensure all row heights are correct."""
        QTimer.singleShot(0, self._sync_row_heights)

    def load_session(self, session: Session, captures: OCRCapture) -> None:
        self.set_session_locked(False)
        self.session_name.setText(session.name)
        
        self.ocr_panel.load_captures(captures)
        self.speech_panel.load_captures(captures)
        self._sync_row_heights()
        # Widths aren't final until the new widgets are laid out; recompute once
        # that settles so rows match the actual panel width (and can shrink).
        self._resync_timer.start()
        
        #  Summarize needs content; Quiz needs a generated summary (it tests on the
        #  lecture material the summary distils). Gate each accordingly.
        has_content = self.ocr_panel.has_content() or self.speech_panel.has_content()
        self.summary_panel.summary_button.setDisabled(not has_content)
        self.summary_panel.summary.setReadOnly(not has_content)
        self.set_quiz_available(bool(session.summary))

        if session.summary:
            self.summary_panel.set_summary(session.summary)
        else:
            self.summary_panel.clear_summary()

    def set_quiz_available(self, available: bool) -> None:
        """Quiz requires a summary to exist first (see the Quiz help chapter). Reflect that
        in the button state AND the tooltip so it's clear why it's disabled — otherwise the
        button silently does nothing after a recording until a summary is made."""
        self.quiz_button.setDisabled(not available)
        self.quiz_button.setToolTip(
            "Generate a quiz from this session"
            if available else "Generate a summary first, then you can create a quiz"
        )
            
    def set_session_locked(self, locked: bool) -> None:
        self.properties_button.setDisabled(locked)
        self.sync_scroll_button.setDisabled(locked)
        
        self.ocr_visibility_button.setDisabled(locked)
        self.speech_visibility_button.setDisabled(locked)
        self.summary_visibility_button.setDisabled(locked)
        self.quiz_button.setDisabled(locked)
        self.record_button.setDisabled(locked)
        
        self.ocr_panel.ocr_button.setDisabled(locked)
        self.speech_panel.speech_button.setDisabled(locked)
        self.summary_panel.summary_button.setDisabled(locked)

        self.ocr_shortcut.setEnabled(not locked)
        self.speech_shortcut.setEnabled(not locked)
        self.summary_shortcut.setEnabled(not locked)

    def set_properties_locked(self, locked: bool) -> None:
        self.properties_button.setDisabled(locked)

    def set_summary_lock(self, locked: bool) -> None:
        """Lock the workspace while a summary is generating. Intentionally leaves the
        panel collapse/expand buttons and per-capture image toggles enabled so the user
        can still scroll, minimize the OCR image, and open/close panels — nothing else."""
        self.properties_button.setDisabled(locked)
        self.record_button.setDisabled(locked)
        self.sync_scroll_button.setDisabled(locked)
        self.quiz_button.setDisabled(locked)

        # Edit-mode toggles (buttons + shortcuts) off; both feeds forced read-only.
        self.ocr_shortcut.setEnabled(not locked)
        self.speech_shortcut.setEnabled(not locked)
        self.summary_shortcut.setEnabled(not locked)
        self.ocr_panel.set_busy(locked)
        self.speech_panel.set_busy(locked)
    
    def clear_panels(self) -> None:
        self.set_session_locked(True)
        # Reset the header back to the placeholder — otherwise deleting the open session
        # (or all sessions) leaves its name stranded in the title bar.
        self.session_name.setText("Select a session")
        self.ocr_panel.clear_captures()
        self.speech_panel.clear_captures()
        self.summary_panel.clear_summary()

    def update_engine_labels(self, ocr_engine: str, speech_engine: str, summarize_engine: str) -> None:
        self.ocr_engine_label.setText(ocr_engine)
        self.speech_engine_label.setText(speech_engine)
        self.summarize_engine_label.setText(summarize_engine)

    def show_connection_warning(self, message: str) -> None:
        if self._banner_dismissed:  # user closed it; stay hidden until cleared/next recording
            return
        self._connection_label.setText(f"⚠  {message}")
        self.connection_banner.setVisible(True)

    def clear_connection_warning(self) -> None:
        self._banner_dismissed = False
        self.connection_banner.setVisible(False)

    def _dismiss_connection_warning(self) -> None:
        # User closed the banner — keep it hidden until the problem clears or a new
        # recording starts, so it doesn't pop back on the next failed chunk.
        self._banner_dismissed = True
        self.connection_banner.setVisible(False)