# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LectureCapture Lite (one-folder build).

Notable bundling concerns handled here:
  * Tesseract-OCR is a separate executable pytesseract shells out to — bundled under
    tesseract/ and wired up in core.resources.configure_bundled_tesseract().
"""

import os

from PyInstaller.utils.hooks import collect_all

TESSERACT_DIR = r"C:\Program Files\Tesseract-OCR"
# console=True surfaces tracebacks/prints while shaking the build out; False for the
# final, windowed exe that ships in the installer.
CONSOLE = False

datas = [("assets", "assets")]
binaries = []
hiddenimports = ["google.genai", "win32timezone"]

# Packages with native libs / data files / dynamic submodules that need full collection.
for pkg in ("google.genai",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Tesseract (the whole install — exe + dependent DLLs + tessdata) -> tesseract/
if os.path.isdir(TESSERACT_DIR):
    datas.append((TESSERACT_DIR, "tesseract"))


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LectureCapture",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icons/logo.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LectureCapture",
)
