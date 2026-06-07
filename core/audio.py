import io
import time
import queue
import threading

import sounddevice as sd
import soundfile as sf
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

RECORD_SAMPLE_RATE = 44100
# After an API failure (e.g. a rate limit) stop calling the API for this long
# before trying again, so a transient 429 doesn't permanently fall back to local.
API_COOLDOWN_SECONDS = 60
# Caps how many recorded chunks may wait for transcription (bounds memory).
MAX_PENDING_CHUNKS = 5
# Chunks whose RMS level is below this are treated as silence and NOT transcribed,
# which stops Whisper/Gemini from hallucinating gibberish over quiet/empty audio.
SILENCE_RMS_THRESHOLD = 0.005


class AudioWorker(QThread):
    chunk_ready = pyqtSignal(float, str)
    engine_fallback = pyqtSignal(str)

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

        # Whisper is loaded lazily, only if/when local transcription actually runs.
        self.model = None

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
        while True:
            item = self._queue.get()
            if item is None:
                break
            audio, chunk_start = item
            if self._is_silent(audio):
                text = ""  # don't transcribe silence (avoids hallucinated gibberish)
                print(f"[Audio timing] chunk@{chunk_start:.1f}s skipped (silent)")
            else:
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

    def _to_wav_bytes(self, audio: np.ndarray) -> bytes:
        buf = io.BytesIO()
        sf.write(buf, audio, RECORD_SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def _to_wav_bytes_16k(self, audio: np.ndarray) -> bytes:
        """Resample to 16kHz and encode as WAV. ~5× smaller than 44100Hz."""
        target = 16000
        n = int(len(audio) * target / RECORD_SAMPLE_RATE)
        audio_16k = np.interp(
            np.linspace(0, len(audio) - 1, n),
            np.arange(len(audio)),
            audio.astype(np.float64),
        ).astype(np.float32)
        buf = io.BytesIO()
        sf.write(buf, audio_16k, target, format="WAV", subtype="PCM_16")
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
                text = self._transcribe_api(self._to_wav_bytes_16k(audio), chunk_start)
                self._emit_engine("gemini")
                return text
            except Exception as e:
                print(f"[Audio] API failed ({e}); using local for ~{API_COOLDOWN_SECONDS}s")
                self._api_cooldown_until = time.time() + API_COOLDOWN_SECONDS
        text = self._transcribe_local(self._to_wav_bytes(audio), chunk_start)
        self._emit_engine("faster-whisper")
        return text

    def _api_available(self) -> bool:
        return bool(self.speech_api_key) and time.time() >= self._api_cooldown_until

    def _emit_engine(self, name: str) -> None:
        if name != self._last_engine:
            self._last_engine = name
            self.engine_fallback.emit(name)

    def _ensure_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            # tiny is ~10x faster than base on CPU with negligible accuracy loss for
            # lecture speech. beam_size=1 (greedy) removes the main latency source.
            self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
        return self.model

    def _transcribe_local(self, wav_bytes: bytes, chunk_start: float) -> str:
        try:
            model = self._ensure_model()
            # faster-whisper accepts a file-like object and resamples to 16 kHz
            # internally. vad_filter drops non-speech segments (extra hallucination guard).
            segments, _info = model.transcribe(io.BytesIO(wav_bytes), beam_size=1, language="en", vad_filter=True)
            out = ""
            for segment in segments:
                out += f"{self._fmt_ts(chunk_start + segment.start)} {segment.text.strip()}\n"
            return out
        except Exception as e:
            print(f"[Audio] local transcription error: {e}")
            return ""

    def _transcribe_api(self, wav_bytes: bytes, chunk_start: float) -> str:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.speech_api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                "Transcribe this audio accurately. Return only the spoken words with no timestamps, labels, or commentary.",
            ],
        )
        transcript = (response.text or "").strip()
        if not transcript:
            return ""
        return f"{self._fmt_ts(chunk_start)} {transcript}\n"

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
