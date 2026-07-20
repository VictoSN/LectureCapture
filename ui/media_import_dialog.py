import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from ui.format_time import FormatClock

# Audio-only containers. No video widget, so we show a placeholder instead.
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}


class MediaImportDialog(QDialog):
    """Preview imported media and pick where transcription starts."""

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import media")
        self.resize(760, 540)
        self._path = path
        self.start_ms = 0
        self._dragging = False

        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)

        layout = QVBoxLayout(self)

        is_audio = os.path.splitext(path)[1].lower() in AUDIO_EXTS
        if is_audio:
            self._preview = QLabel(f"🎧  {os.path.basename(path)}\n\nAudio file, no video preview")
            self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview.setMinimumHeight(320)
        else:
            self._preview = QVideoWidget(self)
            self._preview.setMinimumHeight(320)
            self.player.setVideoOutput(self._preview)
        layout.addWidget(self._preview, 1)

        # Transport row: play/pause, seek slider, time readout.
        transport = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(90)
        self.play_btn.setToolTip("Play or pause the preview.")
        self.play_btn.clicked.connect(self._toggle_play)
        transport.addWidget(self.play_btn)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setToolTip("Scrub through the media to find where transcription should start.")
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self.player.setPosition)
        transport.addWidget(self.slider, 1)

        self.time_label = QLabel("0:00 / 0:00")
        transport.addWidget(self.time_label)
        layout.addLayout(transport)

        # Action row: hint + Cancel / Transcribe-from-here.
        actions = QHBoxLayout()
        self.hint = QLabel("Scrub to where transcription should start.")
        actions.addWidget(self.hint)
        actions.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Cancel the import without transcribing.")
        self.cancel_btn.clicked.connect(self.reject)
        actions.addWidget(self.cancel_btn)
        self.go_btn = QPushButton("Transcribe from here →")
        self.go_btn.setToolTip("Start transcribing from the current playback position.")
        self.go_btn.setDefault(True)
        self.go_btn.clicked.connect(self._confirm)
        actions.addWidget(self.go_btn)
        layout.addLayout(actions)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.setSource(QUrl.fromLocalFile(path))

    # Transport

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText("Pause" if playing else "Play")

    def _on_slider_pressed(self) -> None:
        self._dragging = True

    def _on_slider_released(self) -> None:
        self._dragging = False
        self.player.setPosition(self.slider.value())

    def _on_position(self, ms: int) -> None:
        if not self._dragging:
            self.slider.setValue(ms)
        self._update_time(ms, self.player.duration())
        self.hint.setText(f"Transcription will start at {self._fmt(ms)}.")

    def _on_duration(self, ms: int) -> None:
        self.slider.setRange(0, ms)
        self._update_time(self.player.position(), ms)

    def _update_time(self, pos: int, dur: int) -> None:
        self.time_label.setText(f"{self._fmt(pos)} / {self._fmt(dur)}")

    @staticmethod
    def _fmt(ms: int) -> str:
        return FormatClock(ms / 1000)

    # Result

    def start_seconds(self) -> float:
        return self.start_ms / 1000.0

    def _confirm(self) -> None:
        self.start_ms = self.player.position()
        self.player.stop()
        self.accept()

    def reject(self) -> None:
        self.player.stop()
        super().reject()
