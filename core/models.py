"""Robust faster-whisper model fetching that prevents 'model.bin' errors from a half-written cache.

Frozen builds hit symlink dangles during concurrent downloads (probe + settings + audio).
Never hands CTranslate2 a model until model.bin is a real, non-empty file. A process-wide
lock serialises threads to prevent races into a half-written cache.
"""

import os

# Silence the noisy "symlinks not supported" warning on Windows; behaviour is unaffected.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import time
import threading

_MODEL_FILE = "model.bin"
# Process-wide lock prevents our threads from racing on the same model download.
_lock = threading.Lock()


def _download(model_id: str, local_files_only: bool) -> str:
    # faster-whisper re-exported download_model at top level in newer versions and under
    # .utils in older ones. Support both.
    try:
        from faster_whisper import download_model
    except Exception:
        from faster_whisper.utils import download_model
    return download_model(model_id, local_files_only=local_files_only)


def model_is_complete(model_dir: str) -> bool:
    """True if model.bin exists as a real, non-empty, openable file.
    Rejects dangling-symlink states that caused 'Unable to open file model.bin' errors."""
    if not model_dir:
        return False
    try:
        p = os.path.join(model_dir, _MODEL_FILE)
        return os.path.isfile(p) and os.path.getsize(p) > 0
    except OSError:
        return False


def ensure_model(model_id: str, log=None, attempts: int = 3) -> str | None:
    """Return a local directory with a complete model, or None. Resolves from cache,
    downloads (resumable), verifies model.bin, and retries partial results with backoff.
    Never raises. Callers treat None as model-unavailable distinct from CUDA failure."""
    with _lock:
        # Fast path: already cached and complete. No network touch needed.
        try:
            d = _download(model_id, local_files_only=True)
            if model_is_complete(d):
                return d
        except Exception:
            pass  # not cached yet or cached incomplete. Fall through to a real download.

        delay = 2.0
        for attempt in range(1, attempts + 1):
            try:
                d = _download(model_id, local_files_only=False)
                if model_is_complete(d):
                    if log:
                        log.info("model %s ready at %s", model_id, d)
                    return d
                if log:
                    log.warning("model %s: model.bin missing/empty after download "
                                "(attempt %d/%d)", model_id, attempt, attempts)
            except Exception as e:
                if log:
                    log.warning("model %s download attempt %d/%d failed: %s",
                                model_id, attempt, attempts, e)
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2

        if log:
            log.error("model %s could not be made available after %d attempts",
                      model_id, attempts)
        return None
