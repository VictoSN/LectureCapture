import os
import sys
from pathlib import Path

# App version shown in-app. Keep in sync with MyAppVersion in installer.iss.
APP_VERSION = "3.2.0"


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
