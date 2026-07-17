"""Locate bundled, read-only resources both from source and from a frozen build.

When PyInstaller freezes the app, data files live under ``sys._MEIPASS`` (the bundle's
``_internal`` folder for a one-folder build) rather than next to the source tree.
"""

import os
import sys
from pathlib import Path

# Single source of truth for the app version shown in-app (Help panel footer).
# Keep this in sync with MyAppVersion in installer.iss (Inno Setup can't import Python).
APP_VERSION = "3.1.2"


def resource_root() -> Path:
    """Project root when running from source; the PyInstaller bundle dir when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent  # core/ -> project root


def configure_bundled_tesseract() -> None:
    """In a frozen build, point pytesseract at the bundled Tesseract binary + tessdata
    (pytesseract is only a wrapper; it shells out to tesseract.exe). No-op from source,
    where a system-installed Tesseract on PATH is used instead."""
    if not getattr(sys, "frozen", False):
        return
    tdir = resource_root() / "tesseract"
    exe = tdir / "tesseract.exe"
    if exe.exists():
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = str(exe)
        os.environ.setdefault("TESSDATA_PREFIX", str(tdir / "tessdata"))
