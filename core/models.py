"""Robust faster-whisper model fetching.

The installed (frozen) build hit ``Unable to open file 'model.bin'`` on first launch and
mislabelled it "CUDA acceleration: NOT available". Root cause is the model cache, not CUDA:
faster-whisper resolves a model to ``<hf cache>/.../snapshots/<rev>/model.bin``, which on
Windows is a **symlink** into ``blobs/``. While a download is still completing (or two
downloads race — e.g. the hardware probe and the settings pre-download both pull tiny.en),
that symlink can momentarily dangle, so CTranslate2 fails to open it and the whole GPU probe
throws.

The fix here is to never hand CTranslate2 a model until ``model.bin`` is a real, openable,
non-empty file: download to completion (resumable), verify, and retry a transient/partial
state. A process-wide lock serialises the probe / settings / recording threads so they
don't race each other into a half-written cache.
"""

import os

# Silence the noisy "symlinks not supported" warning on Windows; behaviour is unaffected.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import time
import threading

_MODEL_FILE = "model.bin"
# Serialise downloads within this process. Hugging Face's own per-blob .lock files guard
# cross-process races; this guards our own threads (probe + settings + audio) from kicking
# off duplicate concurrent fetches of the same model and reading it half-written.
_lock = threading.Lock()


def _download(model_id: str, local_files_only: bool) -> str:
    # faster-whisper re-exported download_model at top level in newer versions and under
    # .utils in older ones — support both.
    try:
        from faster_whisper import download_model
    except Exception:
        from faster_whisper.utils import download_model
    return download_model(model_id, local_files_only=local_files_only)


def model_is_complete(model_dir: str) -> bool:
    """True only if model.bin exists and is a real, non-empty, openable file.

    os.path.getsize() follows symlinks and raises OSError on a dangling one, so this also
    rejects the half-downloaded / broken-symlink state that produced 'Unable to open file
    model.bin' in the installed build."""
    if not model_dir:
        return False
    try:
        p = os.path.join(model_dir, _MODEL_FILE)
        return os.path.isfile(p) and os.path.getsize(p) > 0
    except OSError:
        return False


def ensure_model(model_id: str, log=None, attempts: int = 3) -> str | None:
    """Return a local directory holding a COMPLETE model for ``model_id``, or None.

    Resolves instantly from cache when already complete; otherwise downloads (resumable),
    verifies ``model.bin``, and retries a transient/partial result with backoff. Never
    raises — callers treat None as "model unavailable" (offline / cache broken) and report
    that distinctly from a CUDA-runtime failure.
    """
    with _lock:
        # Fast path: already cached and complete — no network touch.
        try:
            d = _download(model_id, local_files_only=True)
            if model_is_complete(d):
                return d
        except Exception:
            pass  # not cached yet (or cached incomplete) — fall through to a real download

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
