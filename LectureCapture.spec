# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LectureCapture (one-folder build).

Notable bundling concerns handled here:
  * NVIDIA CUDA runtime DLLs (cuBLAS/cuDNN/nvrtc) are loaded by CTranslate2 via runtime
    LoadLibrary, so PyInstaller can't auto-detect them — we add them explicitly, keeping
    the nvidia/<pkg>/bin layout that core.cuda_setup globs for.
  * Tesseract-OCR is a separate executable pytesseract shells out to — bundled under
    tesseract/ and wired up in core.resources.configure_bundled_tesseract().
  * Whisper models are NOT bundled; faster-whisper downloads them at runtime.
"""

import glob
import os
import sysconfig

from PyInstaller.utils.hooks import collect_all

SITE = sysconfig.get_paths()["purelib"]
TESSERACT_DIR = r"C:\Program Files\Tesseract-OCR"
# console=True surfaces tracebacks/prints while shaking the build out; False for the
# final, windowed exe that ships in the installer.
CONSOLE = False

datas = [("assets", "assets")]
binaries = []
hiddenimports = ["google.genai", "win32timezone"]

# Packages with native libs / data files / dynamic submodules that need full collection.
for pkg in ("faster_whisper", "ctranslate2", "google.genai", "sumy", "huggingface_hub"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Tesseract (the whole install — exe + dependent DLLs + tessdata) -> tesseract/
if os.path.isdir(TESSERACT_DIR):
    datas.append((TESSERACT_DIR, "tesseract"))

# CUDA runtime DLLs from the nvidia-*-cu12 wheels, preserving nvidia/<pkg>/bin so
# core.cuda_setup can put each bin dir on the DLL search path at runtime.
for bin_dir in glob.glob(os.path.join(SITE, "nvidia", "*", "bin")):
    dest = os.path.relpath(bin_dir, SITE)  # e.g. nvidia\cublas\bin
    for dll in glob.glob(os.path.join(bin_dir, "*.dll")):
        datas.append((dll, dest))

# nltk tokenizer data for sumy's local summary (its data lives in the user profile, not
# the package). PyInstaller's nltk runtime hook adds _MEIPASS/nltk_data to the search path.
try:
    import nltk
    for _base in nltk.data.path:
        _tok = os.path.join(_base, "tokenizers")
        if os.path.isdir(os.path.join(_tok, "punkt")) or os.path.isdir(os.path.join(_tok, "punkt_tab")):
            for _name in ("punkt", "punkt_tab"):
                _src = os.path.join(_tok, _name)
                if os.path.isdir(_src):
                    datas.append((_src, os.path.join("nltk_data", "tokenizers", _name)))
            break
except Exception:
    pass


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
