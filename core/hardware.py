"""Detect the speech-transcription hardware and recommend a Whisper model.

The only reliable way to know the GPU path works is to actually load a model on
CUDA and run an inference — a device can be present yet the cuBLAS/cuDNN runtime
fail to load (see core/cuda_setup). That takes a few seconds, so the probe runs on
a worker thread (HardwareProbeWorker).
"""

import sys
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal


def recommend_model(vram_mb: int | None, gpu_usable: bool) -> str:
    """Pick a sensible default model. Values match the Settings dropdown items."""
    if not gpu_usable:
        return "tiny.en"           # keep CPU transcription real-time
    if vram_mb is None:
        return "distil-large-v3"   # CUDA works but VRAM unknown — safe accurate default
    if vram_mb >= 6000:
        return "distil-large-v3"
    if vram_mb >= 4000:
        return "medium.en"
    return "small.en"


def auto_gpu_model() -> str:
    """Model that the 'Automatic' setting resolves to on a working GPU — tiered by
    VRAM (same logic as the Detect-Hardware recommendation), not always the biggest."""
    _, vram = _query_gpu()
    return recommend_model(vram, True)


def _query_gpu() -> tuple[str | None, int | None]:
    """(name, total VRAM in MB) via nvidia-smi, or (None, None) if unavailable."""
    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # no console flash
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, **kwargs,
        )
        line = (out.stdout or "").strip().splitlines()[0]
        name, mem = [p.strip() for p in line.split(",")]
        return name, int(mem)
    except Exception:
        return None, None


def _cuda_device_count() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def _cuda_usable() -> bool:
    """Load a tiny model on CUDA and run one inference to confirm the runtime works."""
    from core.cuda_setup import prepare_cuda
    if not prepare_cuda():
        return False
    try:
        import numpy as np
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny.en", device="cuda", compute_type="float16")
        list(model.transcribe((np.random.randn(16000) * 0.01).astype(np.float32),
                              beam_size=1, language="en")[0])
        del model
        return True
    except Exception as e:
        print(f"[Hardware] CUDA present but not usable: {e}")
        return False


def probe_hardware() -> tuple[str, str]:
    """Returns (human-readable report, recommended model value for the dropdown)."""
    name, vram = _query_gpu()
    usable = _cuda_usable()
    present = bool(name) or _cuda_device_count() > 0
    rec = recommend_model(vram, usable)

    vram_txt = f"{vram / 1024:.0f} GB" if vram else "unknown VRAM"
    cpu_tip = "Smaller models keep transcription real-time on the CPU."

    if usable:
        body = (
            f"GPU: {name or 'CUDA device'} ({vram_txt})\n"
            "CUDA acceleration: working ✓\n\n"
            f"Recommended model: {rec}\n"
            "Your GPU runs this near real time."
        )
    elif present:
        body = (
            f"GPU: {name or 'CUDA device'} ({vram_txt})\n"
            "CUDA acceleration: NOT available ✗\n"
            "(GPU found, but the CUDA runtime could not load — using CPU.)\n\n"
            f"Recommended model: {rec}\n{cpu_tip}"
        )
    else:
        body = (
            "No CUDA GPU detected — transcription will run on the CPU.\n\n"
            f"Recommended model: {rec}\n{cpu_tip}"
        )
    return body, rec


class HardwareProbeWorker(QThread):
    """Runs probe_hardware() off the GUI thread (it loads a model + runs an inference
    to verify CUDA, which can take a few seconds)."""
    done = pyqtSignal(str, str)   # (report, recommended_model)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            report, rec = probe_hardware()
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.done.emit(report, rec)
