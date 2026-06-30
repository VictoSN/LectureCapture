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
for pkg in ("faster_whisper", "ctranslate2", "google.genai", "huggingface_hub"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Tesseract (the whole install — exe + dependent DLLs + tessdata) -> tesseract/
if os.path.isdir(TESSERACT_DIR):
    datas.append((TESSERACT_DIR, "tesseract"))

# CUDA runtime DLLs from the nvidia-*-cu12 wheels — bundled into the ctranslate2/ folder,
# right beside ctranslate2's native module (which is what loads cuBLAS/cuDNN via runtime
# LoadLibrary). cuDNN 9 ships a SPLIT loader: ctranslate2's own cudnn64_9.dll dlopens the
# heavy sub-DLLs (cudnn_cnn64_9.dll, cudnn_ops64_9.dll, ...), which only the nvidia-cudnn
# wheel provides. In the frozen build those sub-DLLs weren't on the loader's search path,
# so CUDA init silently failed -> CPU fallback (it works from source because the venv keeps
# the whole set together). Co-locating them with ctranslate2 + adding that dir to the DLL
# search path (core/cuda_setup) fixes it. ~1.9 GB, but relocated (NOT duplicated), so the
# build size is unchanged.
for bin_dir in glob.glob(os.path.join(SITE, "nvidia", "*", "bin")):
    for dll in glob.glob(os.path.join(bin_dir, "*.dll")):
        datas.append((dll, "ctranslate2"))

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

# De-duplicate the CUDA runtime. PyInstaller's dependency scan auto-bundles the directly
# linked CUDA DLLs (cublas64_12, cublasLt64_12 [~640 MB!], cudnn_graph/ops) under
# nvidia/<pkg>/bin, but we've already co-located the FULL CUDA set into ctranslate2/ above
# (the only dir core/cuda_setup puts on the DLL search path). The nvidia/ tree is therefore
# never loaded — drop it so the runtime isn't shipped twice (~930 MB of duplicate DLLs).
def _not_redundant_nvidia(entry):
    return not entry[0].replace("\\", "/").lower().startswith("nvidia/")
a.binaries = [e for e in a.binaries if _not_redundant_nvidia(e)]
a.datas = [e for e in a.datas if _not_redundant_nvidia(e)]

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
