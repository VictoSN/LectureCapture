"""Make the pip-installed CUDA 12 runtime (cuBLAS + cuDNN) loadable by CTranslate2.

faster-whisper's GPU path goes through CTranslate2, whose native loader calls
``LoadLibrary("cublas64_12.dll")`` directly. That ignores ``os.add_dll_directory``
and only searches ``PATH``, so on Windows the DLLs shipped by the
``nvidia-cublas-cu12`` / ``nvidia-cudnn-cu12`` wheels are invisible unless we put
their ``bin`` folders on ``PATH`` ourselves. We do both (PATH + add_dll_directory)
to be safe across loader code paths.
"""

import os
import sys
import glob
import sysconfig

# Cache the result so the (cheap) path setup + device probe runs only once.
_prepared: bool | None = None


def prepare_cuda() -> bool:
    """Add the bundled CUDA runtime to the DLL search path and report whether a
    usable CUDA device is present. Idempotent; safe to call from any thread.

    Returns True only if a CUDA device exists AND the runtime DLL folders were
    found — i.e. it's worth *attempting* a GPU model. The actual cuBLAS load can
    still fail later (e.g. an unsupported GPU), so callers must keep a CPU
    fallback around a real inference, not trust this alone.
    """
    global _prepared
    if _prepared is not None:
        return _prepared

    _prepared = False
    try:
        # The nvidia-*-cu12 wheels ship their DLLs under <base>/nvidia/<pkg>/bin. From
        # source that's site-packages; in a frozen build they're bundled under _MEIPASS.
        base = sys._MEIPASS if getattr(sys, "frozen", False) else sysconfig.get_paths()["purelib"]
        dll_dirs = glob.glob(os.path.join(base, "nvidia", "*", "bin"))
        if dll_dirs:
            os.environ["PATH"] = os.pathsep.join(dll_dirs) + os.pathsep + os.environ.get("PATH", "")
            for d in dll_dirs:
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass

        import ctranslate2
        has_gpu = ctranslate2.get_cuda_device_count() > 0
        _prepared = bool(dll_dirs) and has_gpu
    except Exception as e:  # pragma: no cover - defensive: never block startup
        print(f"[CUDA] setup skipped: {e}")
        _prepared = False

    return _prepared
