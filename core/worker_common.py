import time

# Cooldown before retrying API after a failure (e.g. rate limit).
API_COOLDOWN_SECONDS = 60


class RecordingWorkerMixin:
    """Mixin for QThread workers. Call _init_worker_common() from __init__ after setting the API key."""

    def _init_worker_common(self) -> None:
        # Pause: nothing captured while paused; paused time subtracted from timestamps so timeline stays continuous.
        self._paused = False
        self._paused_total = 0.0
        self._pause_started = None
        # API fallback state. Cooldown-based instead of permanently sticky.
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
