"""State and behaviour shared by the recording workers (OCRWorker + AudioWorker).

Both workers pause the same way — accumulating paused time so slide and speech
timestamps stay aligned with each other across pauses — report engine changes the
same way (emit only on change, so the footer label doesn't flap), and back off the
API the same way after a failure (a cooldown rather than a permanently sticky
fallback to local).
"""

import time

# After an API failure (e.g. a rate limit) stop calling the API for this long
# before trying again, so a transient 429 doesn't permanently fall back to local.
API_COOLDOWN_SECONDS = 60


class RecordingWorkerMixin:
    """Mixed into the QThread workers. Call _init_worker_common() from __init__,
    after the API key is assigned — _last_engine reads the engine_name property,
    which depends on it."""

    def _init_worker_common(self) -> None:
        # Pause support: while paused nothing is captured/transcribed, and the
        # total paused time is subtracted from timestamps so the session timeline
        # stays continuous across pauses instead of jumping by the pause length.
        self._paused = False
        self._paused_total = 0.0
        self._pause_started = None
        # API fallback state — cooldown-based instead of permanently sticky.
        self._api_cooldown_until = 0.0
        self._last_engine = self.engine_name

    def set_paused(self, paused: bool) -> None:
        """Pause/resume capture. Accumulates paused time so timestamps exclude it."""
        if paused and not self._paused:
            self._pause_started = time.time()
        elif not paused and self._paused and self._pause_started is not None:
            self._paused_total += time.time() - self._pause_started
            self._pause_started = None
        self._paused = paused

    def _start_api_cooldown(self) -> None:
        self._api_cooldown_until = time.time() + API_COOLDOWN_SECONDS

    def _emit_engine(self, name: str) -> None:
        if name != self._last_engine:
            self._last_engine = name
            self.engine_fallback.emit(name)
