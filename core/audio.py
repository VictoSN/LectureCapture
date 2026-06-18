import io
import time
import queue
import threading

import sounddevice as sd
import soundfile as sf
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

RECORD_SAMPLE_RATE = 44100
# faster-whisper wants 16 kHz mono; resampling there cuts both local decode work
# and the API payload size (~5× smaller than 44.1 kHz).
WHISPER_SAMPLE_RATE = 16000
# After an API failure (e.g. a rate limit) stop calling the API for this long
# before trying again, so a transient 429 doesn't permanently fall back to local.
API_COOLDOWN_SECONDS = 60
# Caps how many recorded chunks may wait for transcription (bounds memory).
MAX_PENDING_CHUNKS = 5
# Chunks whose RMS level is below this are treated as silence and NOT transcribed,
# which stops Whisper/Gemini from hallucinating gibberish over quiet/empty audio.
SILENCE_RMS_THRESHOLD = 0.005

# Local Whisper model per device. On a CUDA GPU we can afford a large, highly
# accurate English model in real time (distil-large-v3 ≈ large-v3 accuracy at a
# fraction of the cost); on CPU we fall back to the fast English tiny model.
# English-only, so transcription is always English without extra config.
CPU_WHISPER_MODEL = "tiny.en"

# Out-of-the-box model when the user hasn't picked one. A balanced "medium" default
# (good accuracy, real-time on a GPU and most CPUs); Detect Hardware in Settings can
# recommend/apply a better one for the detected device. (The retired "auto" value is
# still handled below as a safety net for settings saved by older builds.)
DEFAULT_SPEECH_MODEL = "small.en"


class AudioWorker(QThread):
    chunk_ready = pyqtSignal(float, str)
    # Emitted when a (non-silent) chunk starts transcribing, so the UI can show a
    # "transcribing…" placeholder on the slide the speech will land on. The matching
    # chunk_ready (same timestamp) clears it.
    chunk_pending = pyqtSignal(float)
    engine_fallback = pyqtSignal(str)
    # An API attempt failed mid-recording. Carries a status from core.api_errors
    # ("invalid_key" | "no_connection" | "other") so the UI can warn the user.
    api_error = pyqtSignal(str)

    def __init__(self, session_id: int, base_dir: str, interval: int, device, start_time, offset: int, speech_api_key: str = "", speech_model: str = DEFAULT_SPEECH_MODEL) -> None:
        super().__init__()
        self._running = True

        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.speech_api_key = speech_api_key
        # Which local Whisper model to use. A concrete id (e.g. "small.en"); a legacy
        # "auto" is still accepted and resolved per-device in _ensure_model.
        self.speech_model = speech_model or DEFAULT_SPEECH_MODEL

        # API fallback state — cooldown-based instead of permanently sticky.
        self._api_cooldown_until = 0.0
        self._last_engine = self.engine_name

        # Whisper is loaded lazily, only if/when local transcription actually runs.
        self.model = None
        # Set once the local model is loaded, so the footer can show GPU vs CPU.
        self._local_engine_label = "faster-whisper"

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
        # while a chunk is transcribed.
        self._queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_CHUNKS)
        self._consumer = None

    # ---- device selection ----------------------------------------------

    def find_loopback_device(self):
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
        frames_per_chunk = int(self.interval * RECORD_SAMPLE_RATE)
        cb_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            mono = indata.mean(axis=1) if (indata.ndim > 1 and indata.shape[1] > 1) else indata.reshape(-1)
            cb_queue.put(mono.copy())

        # The stream is opened AND closed on this thread (the context manager),
        # so there are no cross-thread sounddevice calls to crash PortAudio.
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
        # When local is the speech engine, load + warm the model now (on this
        # thread) so the slow first-inference CUDA warmup overlaps with the first
        # chunk being recorded, instead of stalling that chunk's transcription.
        if not self.speech_api_key:
            try:
                self._ensure_model()
            except Exception as e:
                print(f"[Audio] model preload failed: {e}")
        while True:
            item = self._queue.get()
            if item is None:
                break
            audio, chunk_start = item
            if self._is_silent(audio):
                text = ""  # don't transcribe silence (avoids hallucinated gibberish)
                print(f"[Audio timing] chunk@{chunk_start:.1f}s skipped (silent)")
            else:
                # Tell the UI a chunk for this moment is being transcribed.
                self.chunk_pending.emit(chunk_start)
                t0 = time.time()
                try:
                    text = self._transcribe(audio, chunk_start)
                except Exception as e:
                    print(f"[Audio] transcription error: {e}")
                    text = ""
                print(f"[Audio timing] chunk@{chunk_start:.1f}s transcribed in {time.time()-t0:.2f}s")
            # Attach this speech to the slide on screen when the audio window STARTED.
            # Using chunk_start (not chunk_start+interval) means we look up whatever
            # slide was active when the person began speaking, which is almost always
            # the right one — even if a transition happened near the end of the chunk.
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
        buf = io.BytesIO()
        sf.write(buf, self._to_16k_array(audio), WHISPER_SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"[{m}:{s:02d}]"

    def _transcribe(self, audio: np.ndarray, chunk_start: float) -> str:
        if self._api_available():
            try:
                # Send a downsampled 16kHz WAV — ~5× smaller payload than 44100Hz,
                # which significantly cuts Gemini API round-trip latency.
                text, model = self._transcribe_api(self._to_wav_bytes_16k(audio), chunk_start)
                from core.gemini import pretty_model
                self._emit_engine(pretty_model(model))
                return text
            except Exception as e:
                print(f"[Audio] API failed ({e}); using local for ~{API_COOLDOWN_SECONDS}s")
                self._api_cooldown_until = time.time() + API_COOLDOWN_SECONDS
                from core.api_errors import classify_api_error
                self.api_error.emit(classify_api_error(e))
        text = self._transcribe_local(audio, chunk_start)
        self._emit_engine(self._local_engine_label)
        return text

    def _api_available(self) -> bool:
        return bool(self.speech_api_key) and time.time() >= self._api_cooldown_until

    def _emit_engine(self, name: str) -> None:
        if name != self._last_engine:
            self._last_engine = name
            self.engine_fallback.emit(name)

    def _ensure_model(self):
        if self.model is not None:
            return self.model
        from faster_whisper import WhisperModel

        # The chosen model is honoured on whichever device is available. A legacy
        # "auto" (from settings saved by older builds) resolves per-device below
        # (big on GPU, tiny on CPU); new installs always store a concrete model.
        chosen = self.speech_model if self.speech_model != "auto" else None

        # Prefer the GPU: a CUDA device lets us run a large, accurate English model in
        # real time. "Device present" doesn't guarantee the cuBLAS/cuDNN runtime
        # actually loads (e.g. unsupported GPU), so we warm up with a real inference
        # and fall back to CPU if anything in the GPU path raises.
        from core.cuda_setup import prepare_cuda
        if prepare_cuda():
            # "Automatic" → best model for the detected GPU's VRAM (not always the biggest).
            from core.hardware import auto_gpu_model
            model_id = chosen or auto_gpu_model()
            try:
                t0 = time.time()
                # On first use this downloads the model (can be hundreds of MB) before it
                # loads — surface that so the empty transcript doesn't look like a freeze.
                self._emit_engine(f"faster-whisper · loading {model_id}…")
                model = WhisperModel(model_id, device="cuda", compute_type="float16")
                self._warmup(model)
                print(f"[Audio] loaded {model_id} on GPU in {time.time()-t0:.1f}s")
                self.model = model
                self._local_engine_label = f"faster-whisper · {model_id} · GPU"
                self._emit_engine(self._local_engine_label)
                return self.model
            except Exception as e:
                print(f"[Audio] GPU model unavailable ({e}); falling back to CPU")

        # CPU fallback (int8, greedy). "auto" → tiny.en, else the user's choice (which
        # may be slow on CPU — that's their call; the UI flags GPU-oriented models).
        model_id = chosen or CPU_WHISPER_MODEL
        self._emit_engine(f"faster-whisper · loading {model_id}…")
        self.model = WhisperModel(model_id, device="cpu", compute_type="int8")
        self._local_engine_label = f"faster-whisper · {model_id} · CPU"
        self._emit_engine(self._local_engine_label)
        return self.model

    def _warmup(self, model) -> None:
        # First CUDA inference JITs kernels / autotunes cuDNN (several seconds). Run a
        # short dummy clip (no VAD, so the encoder definitely runs) to pay that cost
        # up front rather than on the user's first real chunk.
        dummy = (np.random.randn(WHISPER_SAMPLE_RATE).astype(np.float32)) * 0.01
        list(model.transcribe(dummy, beam_size=1, language="en")[0])

    def _transcribe_local(self, audio: np.ndarray, chunk_start: float) -> str:
        try:
            model = self._ensure_model()
            # Feed a 16 kHz float32 array directly (no WAV encode/decode round-trip).
            # vad_filter drops non-speech segments (extra hallucination guard).
            segments, _info = model.transcribe(
                self._to_16k_array(audio), beam_size=1, language="en", vad_filter=True
            )
            out = ""
            for segment in segments:
                out += f"{self._fmt_ts(chunk_start + segment.start)} {segment.text.strip()}\n"
            return out
        except Exception as e:
            print(f"[Audio] local transcription error: {e}")
            return ""

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
        return "gemini" if self.speech_api_key else "faster-whisper"

    def stop(self) -> None:
        self._running = False
        # Drop chunks still waiting to be transcribed so shutdown is quick, then
        # wake the consumer. The capture loop notices _running and closes its own
        # stream within ~0.2s — no cross-thread sounddevice calls.
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
