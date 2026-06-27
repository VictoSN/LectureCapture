import io
import time
import queue
import threading

import numpy as np

# sounddevice (PortAudio) and soundfile are imported lazily inside the methods that use
# them — NOT here. Importing sounddevice costs ~0.5s (PortAudio init) and this module is
# imported at app startup via main_window, yet audio devices are only touched once a
# recording actually runs. Deferring keeps that cost off every launch.

from PyQt6.QtCore import QThread, pyqtSignal

RECORD_SAMPLE_RATE = 44100
# 16 kHz mono cuts the API payload size ~5× compared to 44.1 kHz.
WHISPER_SAMPLE_RATE = 16000
# After an API failure stop calling the API for this long before trying again.
API_COOLDOWN_SECONDS = 60
# Caps how many recorded chunks may wait for transcription (bounds memory).
MAX_PENDING_CHUNKS = 5
# Chunks whose RMS level is below this are treated as silence and NOT sent to
# the API, which stops Gemini from hallucinating gibberish over quiet audio.
SILENCE_RMS_THRESHOLD = 0.005


class AudioWorker(QThread):
    chunk_ready = pyqtSignal(float, str)
    # Emitted when a (non-silent) chunk starts transcribing, so the UI can show a
    # "transcribing…" placeholder on the slide the speech will land on.
    chunk_pending = pyqtSignal(float)
    engine_fallback = pyqtSignal(str)
    # An API attempt failed mid-recording. Carries a status from core.api_errors
    # ("invalid_key" | "no_connection" | "other") so the UI can warn the user.
    api_error = pyqtSignal(str)

    def __init__(self, session_id: int, base_dir: str, interval: int, device, start_time, offset: int, speech_api_key: str = "") -> None:
        super().__init__()
        self._running = True

        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.speech_api_key = speech_api_key

        # API fallback state — cooldown-based instead of permanently sticky.
        self._api_cooldown_until = 0.0
        self._last_engine = self.engine_name

        # Decode the device selection (may be int, dict, or None).
        if isinstance(device, dict):
            self.device_type = device.get("type", "microphone")
            self.device_id = device.get("device_id")
        elif isinstance(device, int):
            self.device_type = "microphone"
            self.device_id = device
        else:
            self.device_type = "microphone"
            self.device_id = None

        self.start_time = start_time
        self.offset = offset

        # Recorded chunks waiting to be transcribed. A consumer thread drains this
        # so capture (which runs continuously in the audio callback) never pauses
        # while a chunk is being sent to the API.
        self._queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_CHUNKS)
        self._consumer = None

    # ---- device selection ----------------------------------------------

    def find_loopback_device(self):
        import sounddevice as sd
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                name = device["name"].lower()
                if "wasapi" in name or "stereo mix" in name or "loopback" in name:
                    return i
        try:
            default = sd.default.device[0]
            if default is not None:
                return default
        except Exception:
            pass
        return None

    def _resolve_input(self):
        import sounddevice as sd
        device = self.find_loopback_device() if self.device_type == "loopback" else self.device_id
        try:
            info = sd.query_devices(device, "input")
            max_ch = int(info.get("max_input_channels", 1))
        except Exception:
            max_ch = 1
        return device, (2 if max_ch >= 2 else 1)

    # ---- capture (producer) --------------------------------------------

    def run(self) -> None:
        self._consumer = threading.Thread(target=self._consume, daemon=True)
        self._consumer.start()
        try:
            self._capture()
        except Exception as e:
            print(f"[Audio] capture stopped: {e}")
        finally:
            try:
                self._queue.put_nowait(None)  # tell the consumer to finish
            except queue.Full:
                pass
            self._consumer.join(timeout=5)

    def _capture(self) -> None:
        device, channels = self._resolve_input()
        # Try the resolved config, then progressively safer fallbacks.
        for dev, ch in [(device, channels), (device, 1), (None, 1)]:
            if not self._running:
                return
            try:
                self._run_stream(dev, ch)
                return
            except Exception as e:
                print(f"[Audio] input failed (device={dev}, {ch}ch): {e}")
        print("[Audio] no usable audio input")

    def _run_stream(self, device, channels) -> None:
        import sounddevice as sd
        frames_per_chunk = int(self.interval * RECORD_SAMPLE_RATE)
        cb_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            mono = indata.mean(axis=1) if (indata.ndim > 1 and indata.shape[1] > 1) else indata.reshape(-1)
            cb_queue.put(mono.copy())

        with sd.InputStream(samplerate=RECORD_SAMPLE_RATE, channels=channels, device=device, dtype="float32", callback=callback):
            blocks, blen = [], 0
            while self._running:
                try:
                    block = cb_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                blocks.append(block)
                blen += len(block)
                if blen < frames_per_chunk:
                    continue
                buf = np.concatenate(blocks)
                while len(buf) >= frames_per_chunk:
                    chunk = buf[:frames_per_chunk].copy()
                    buf = buf[frames_per_chunk:]
                    chunk_start = time.time() - self.start_time + self.offset - self.interval
                    try:
                        self._queue.put_nowait((chunk, chunk_start))
                    except queue.Full:
                        print("[Audio] transcription backlog full, dropping chunk")
                blocks = [buf] if len(buf) else []
                blen = len(buf)

    # ---- transcription (consumer) --------------------------------------

    def _consume(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            audio, chunk_start = item
            if self._is_silent(audio):
                text = ""
                print(f"[Audio timing] chunk@{chunk_start:.1f}s skipped (silent)")
            else:
                self.chunk_pending.emit(chunk_start)
                t0 = time.time()
                try:
                    text = self._transcribe(audio, chunk_start)
                except Exception as e:
                    print(f"[Audio] transcription error: {e}")
                    text = ""
                print(f"[Audio timing] chunk@{chunk_start:.1f}s transcribed in {time.time()-t0:.2f}s")
            self.chunk_ready.emit(chunk_start, text)

    def _is_silent(self, audio: np.ndarray) -> bool:
        if audio.size == 0:
            return True
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
        return rms < SILENCE_RMS_THRESHOLD

    def _to_16k_array(self, audio: np.ndarray) -> np.ndarray:
        """Resample 44.1 kHz mono float32 down to 16 kHz mono float32."""
        n = int(len(audio) * WHISPER_SAMPLE_RATE / RECORD_SAMPLE_RATE)
        return np.interp(
            np.linspace(0, len(audio) - 1, n),
            np.arange(len(audio)),
            audio.astype(np.float64),
        ).astype(np.float32)

    def _to_wav_bytes_16k(self, audio: np.ndarray) -> bytes:
        """Resample to 16kHz and encode as WAV. ~5× smaller than 44100Hz."""
        import soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, self._to_16k_array(audio), WHISPER_SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"[{m}:{s:02d}]"

    def _transcribe(self, audio: np.ndarray, chunk_start: float) -> str:
        if not self._api_available():
            return ""
        try:
            text, model = self._transcribe_api(self._to_wav_bytes_16k(audio), chunk_start)
            from core.gemini import pretty_model
            self._emit_engine(pretty_model(model))
            return text
        except Exception as e:
            print(f"[Audio] API failed ({e}); cooling down for ~{API_COOLDOWN_SECONDS}s")
            self._api_cooldown_until = time.time() + API_COOLDOWN_SECONDS
            from core.api_errors import classify_api_error
            self.api_error.emit(classify_api_error(e))
            return ""

    def _api_available(self) -> bool:
        return bool(self.speech_api_key) and time.time() >= self._api_cooldown_until

    def _emit_engine(self, name: str) -> None:
        if name != self._last_engine:
            self._last_engine = name
            self.engine_fallback.emit(name)

    def _transcribe_api(self, wav_bytes: bytes, chunk_start: float) -> tuple[str, str]:
        """Returns (formatted_transcript, model_id)."""
        from google.genai import types
        from core.gemini import generate, FREQUENT_MODEL_CHAIN
        response, model = generate(
            self.speech_api_key,
            [
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                "Transcribe this audio accurately. Return only the spoken words with no timestamps, labels, or commentary.",
            ],
            chain=FREQUENT_MODEL_CHAIN,
        )
        transcript = (response.text or "").strip()
        if not transcript:
            return "", model
        return f"{self._fmt_ts(chunk_start)} {transcript}\n", model

    @property
    def engine_name(self) -> str:
        return "gemini" if self.speech_api_key else ""

    def stop(self) -> None:
        self._running = False
        # Drop chunks still waiting to be transcribed so shutdown is quick.
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
