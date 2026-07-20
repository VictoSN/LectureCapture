import os
import sys
import glob
import sysconfig

# Cache the result so the (cheap) path setup + device probe runs only once.
_prepared: bool | None = None


def prepare_cuda() -> bool:
    """Add CUDA DLLs to the search path and report whether a usable device exists.
    Idempotent and thread-safe. Returns True only when device and DLLs are found. Callers
    must still keep a CPU fallback since cuBLAS may fail at inference time."""
    global _prepared
    if _prepared is not None:
        return _prepared

    _prepared = False
    try:
        # CUDA DLLs under site-packages/nvidia/*/bin in source, or next to ctranslate2 when frozen.
        if getattr(sys, "frozen", False):
            ct2 = os.path.join(sys._MEIPASS, "ctranslate2")
            dll_dirs = [ct2] if os.path.isdir(ct2) else []
        else:
            base = sysconfig.get_paths()["purelib"]
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
