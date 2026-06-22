"""Lightweight file logging so failures in the shipped build aren't invisible.

The installer build is frozen with ``console=False`` (see LectureCapture.spec), which
discards stdout/stderr — so every diagnostic ``print()`` in the app vanishes in an
installed copy. When the GPU/model path fails on a user's machine there is nothing to look
at. This mirrors those messages to a rotating log file under
``%APPDATA%/LectureCapture/logs`` so first-run issues can be diagnosed from an install.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler

_configured = False


def _log_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "LectureCapture", "logs")
    os.makedirs(d, exist_ok=True)
    return d


def get_logger() -> logging.Logger:
    """Return the shared app logger, configuring a rotating file handler once.

    Safe to call from any thread; configuration is idempotent. Never raises — if the log
    file can't be opened we fall back to stderr only, since logging must not block startup.
    """
    global _configured
    logger = logging.getLogger("lecturecapture")
    if _configured:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
    try:
        fh = RotatingFileHandler(
            os.path.join(_log_dir(), "lecturecapture.log"),
            maxBytes=512_000, backupCount=2, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # never let logging setup break the app
    sh = logging.StreamHandler()  # visible when run from source / a console=True dev build
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    _configured = True
    return logger


def install_excepthook() -> None:
    """Route uncaught exceptions (main thread + threads) into the log file, so a windowed
    build doesn't die silently."""
    log = get_logger()

    def _hook(exc_type, exc, tb):
        log.error("Uncaught exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
    try:
        import threading
        threading.excepthook = lambda a: log.error(
            "Uncaught thread exception in %s", a.thread,
            exc_info=(a.exc_type, a.exc_value, a.exc_traceback),
        )
    except Exception:
        pass
