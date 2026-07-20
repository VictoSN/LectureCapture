import os

# Silence the noisy "symlinks not supported" warning on Windows.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import fnmatch
import shutil
import time
import threading

_MODEL_FILE = "model.bin"
_lock = threading.Lock()

# Model shorthands to Hugging Face repo IDs.
_MODEL_REPOS: dict[str, str] = {
    "tiny.en":              "Systran/faster-whisper-tiny.en",
    "tiny":                 "Systran/faster-whisper-tiny",
    "base.en":              "Systran/faster-whisper-base.en",
    "base":                 "Systran/faster-whisper-base",
    "small.en":             "Systran/faster-whisper-small.en",
    "small":                "Systran/faster-whisper-small",
    "medium.en":            "Systran/faster-whisper-medium.en",
    "medium":               "Systran/faster-whisper-medium",
    "large-v1":             "Systran/faster-whisper-large-v1",
    "large-v2":             "Systran/faster-whisper-large-v2",
    "large-v3":             "Systran/faster-whisper-large-v3",
    "large":                "Systran/faster-whisper-large-v3",
    "distil-large-v2":      "Systran/faster-distil-whisper-large-v2",
    "distil-medium.en":     "Systran/faster-distil-whisper-medium.en",
    "distil-small.en":      "Systran/faster-distil-whisper-small.en",
    "distil-large-v3":      "Systran/faster-distil-whisper-large-v3",
}


def _repo_candidates(model_id: str) -> list[str]:
    """Map a model shorthand to the corresponding HF repo IDs."""
    candidates: list[str] = []
    if model_id in _MODEL_REPOS:
        candidates.append(_MODEL_REPOS[model_id])
    if "/" in model_id and model_id not in candidates:
        candidates.append(model_id)
    return candidates


def _download(model_id: str, local_files_only: bool) -> str:
    # faster-whisper moved download_model from .utils to the top level in newer versions.
    try:
        from faster_whisper import download_model
    except Exception:
        from faster_whisper.utils import download_model
    return download_model(model_id, local_files_only=local_files_only)


def model_is_complete(model_dir: str) -> bool:
    """True if model.bin is a real, non-empty file."""
    if not model_dir:
        return False
    p = os.path.join(model_dir, _MODEL_FILE)
    for _ in range(3):
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def _cached_complete(model_id: str) -> str | None:
    """Cached and complete, or None."""
    try:
        d = _download(model_id, local_files_only=True)
    except Exception:
        return None
    return d if model_is_complete(d) else None


def _hub_unreachable_reason(model_id: str) -> str | None:
    """None if reachable, error string if not."""
    try:
        from huggingface_hub import HfApi
        HfApi().model_info("bert-base-uncased", timeout=5)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _find_complete_snapshot(model_id: str, log=None) -> str | None:
    """Scan the local HF cache for a usable snapshot."""
    from huggingface_hub.constants import HF_HUB_CACHE
    repos = _repo_candidates(model_id)
    cache_dir = os.environ.get("HF_HUB_CACHE") or HF_HUB_CACHE
    for repo_id in repos:
        folder = "models--" + repo_id.replace("/", "--")
        snapshots_dir = os.path.join(cache_dir, folder, "snapshots")
        if not os.path.isdir(snapshots_dir):
            continue
        try:
            for sha in os.listdir(snapshots_dir):
                snap = os.path.join(snapshots_dir, sha)
                if model_is_complete(snap):
                    if log:
                        log.info("found cached snapshot for %s at %s", model_id, snap)
                    return snap
        except OSError:
            continue
    return None


class _disabled_tqdm:
    """Dummy tqdm.  In frozen builds stdout is None and the real tqdm crashes."""
    @staticmethod
    def __init__(*args, **kwargs): pass
    @staticmethod
    def __enter__(): return _disabled_tqdm()
    @staticmethod
    def __exit__(*args): pass
    @staticmethod
    def update(n=1): pass
    @staticmethod
    def close(): pass
    @staticmethod
    def refresh(): pass


# Only download model files, not repo cruft.
_DIRECT_ALLOW_PATTERNS = [
    "config.json", "preprocessor_config.json",
    "model.bin", "tokenizer.json", "vocabulary.*",
]


def _direct_download(model_id: str, log=None) -> str | None:
    """Download model files individually via hf_hub_download.  Windows relative
    symlinks are replaced with real file copies so they always resolve."""
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.constants import HF_HUB_CACHE

    repos = _repo_candidates(model_id)
    if not repos:
        return None
    cache_dir = os.environ.get("HF_HUB_CACHE") or HF_HUB_CACHE

    for repo_id in repos:
        # Get file list and commit hash from the Hub.
        try:
            api = HfApi()
            info = api.model_info(repo_id, expand=["siblings", "sha"])
        except Exception as e:
            if log:
                log.warning("direct-download: model_info(%s) failed: %s", repo_id, e)
            continue

        sha = getattr(info, "sha", None)
        siblings = getattr(info, "siblings", None)
        if not sha or not siblings:
            continue

        folder = "models--" + repo_id.replace("/", "--")
        snapshot_dir = os.path.join(cache_dir, folder, "snapshots", sha)

        filenames = [s.rfilename for s in siblings
                     if any(fnmatch.fnmatch(s.rfilename, p) for p in _DIRECT_ALLOW_PATTERNS)]
        if log:
            log.info("direct-download: fetching %d files from %s (commit %.12s)",
                     len(filenames), repo_id, sha)

        # Download each file with tqdm disabled for frozen builds.
        for filename in filenames:
            try:
                hf_hub_download(repo_id=repo_id, filename=filename, revision=sha,
                                tqdm_class=_disabled_tqdm)
            except Exception as e:
                if filename == _MODEL_FILE:
                    if log:
                        log.error("direct-download: %s failed: %s", filename, e)
                    break
                if log:
                    log.warning("direct-download: %s skipped (%s)", filename, e)
        else:
        # Replace broken Windows symlinks with file copies.
            for filename in filenames:
                ptr = os.path.join(snapshot_dir, filename)
                try:
                    if os.path.islink(ptr) and not os.path.isfile(ptr):
                        target = os.readlink(ptr)
                        blob = os.path.normpath(os.path.join(os.path.dirname(ptr), target))
                        if os.path.isfile(blob):
                            os.remove(ptr)
                            shutil.copy2(blob, ptr)
                except OSError:
                    pass

            if model_is_complete(snapshot_dir):
                if log:
                    log.info("model %s ready via direct download at %s", model_id, snapshot_dir)
                return snapshot_dir

    return None


def ensure_model(model_id: str, log=None, attempts: int = 3) -> str | None:
    """Return a directory with a complete model, or None.  Never raises."""
    with _lock:
        # Already cached.
        d = _cached_complete(model_id)
        if d:
            return d

        # snapshot_download.
        try:
            d = _download(model_id, local_files_only=False)
        except Exception:
            d = None
        if d and model_is_complete(d):
            if log:
                log.info("model %s ready at %s", model_id, d)
            return d

        # Direct per-file download fixes broken Windows symlinks.
        d = _direct_download(model_id, log)
        if d:
            return d

        # Last resort, scan the local cache.
        d = _find_complete_snapshot(model_id, log)
        if d:
            return d

        if log:
            log.error("model %s could not be made available", model_id)
        return None
