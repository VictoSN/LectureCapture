import io
import time
import queue
import threading

import numpy as np

# sounddevice (PortAudio) and soundfile are imported lazily inside the methods that use
# them — NOT here. Importing sounddevice costs ~0.5s (PortAudio init) and this module is
# imported at app startup via main_window, yet audio devices are only touched once a
# recording actually runs. Deferring keeps that cost off every launch (tests/PERFORMANCE.md).

from PyQt6.QtCore import QThread, pyqtSignal

from models.lecture import OCRCapture

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

        # Pause support. While paused, captured audio is discarded (not transcribed), and
        # the total paused time is subtracted from chunk timestamps so the transcript
        # timeline stays continuous across pauses instead of jumping by the pause length.
        self._paused = False
        self._paused_total = 0.0
        self._pause_started = None

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
        # Once the GPU model load has failed we stop re-attempting it on every chunk.
        # Without this, a failed load left self.model=None and each following chunk re-ran
        # the whole GPU path, flapping the footer between the GPU model and CPU fallback.
        self._gpu_disabled = False

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

        # The stream is opened AND closed on this thread (the context manager),
        # so there are no cross-thread sounddevice calls to crash PortAudio.
        with sd.InputStream(samplerate=RECORD_SAMPLE_RATE, channels=channels, device=device, dtype="float32", callback=callback):
            blocks, blen = [], 0
            while self._running:
                try:
                    block = cb_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                # While paused, drop captured audio and any partial buffer so nothing
                # recorded during the pause is transcribed or leaks into the next chunk.
                if self._paused:
                    blocks, blen = [], 0
                    continue
                blocks.append(block)
                blen += len(block)
                if blen < frames_per_chunk:
                    continue
                buf = np.concatenate(blocks)
                while len(buf) >= frames_per_chunk:
                    chunk = buf[:frames_per_chunk].copy()
                    buf = buf[frames_per_chunk:]
                    chunk_start = time.time() - self.start_time + self.offset - self.interval - self._paused_total
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
        from core.models import ensure_model
        from core.applog import get_logger
        log = get_logger()

        # The chosen model is honoured on whichever device is available. A legacy
        # "auto" (from settings saved by older builds) resolves per-device below
        # (big on GPU, tiny on CPU); new installs always store a concrete model.
        chosen = self.speech_model if self.speech_model != "auto" else None

        # Prefer the GPU: a CUDA device lets us run a large, accurate English model in
        # real time. "Device present" doesn't guarantee the cuBLAS/cuDNN runtime
        # actually loads (e.g. unsupported GPU), so we fall back to CPU if it raises.
        from core.cuda_setup import prepare_cuda
        if prepare_cuda() and not self._gpu_disabled:
            # "Automatic" → best model for the detected GPU's VRAM (not always the biggest).
            from core.hardware import auto_gpu_model
            model_id = chosen or auto_gpu_model()
            # On first use this downloads the model (can be hundreds of MB) before it
            # loads — surface that so the empty transcript doesn't look like a freeze.
            self._emit_engine(f"faster-whisper · loading {model_id}…")
            # Make sure model.bin is fully on disk *before* handing it to CUDA — a partial /
            # broken-symlink cache is what masqueraded as a CUDA failure on first launch.
            model_dir = ensure_model(model_id, log)
            if model_dir is not None:
                try:
                    t0 = time.time()
                    model = WhisperModel(model_dir, device="cuda", compute_type="float16")
                    self._warmup(model)
                    log.info("loaded %s on GPU in %.1fs", model_id, time.time() - t0)
                    self.model = model
                    self._local_engine_label = f"faster-whisper · {model_id} · GPU"
                    self._emit_engine(self._local_engine_label)
                    return self.model
                except Exception as e:
                    log.warning("GPU model load failed (%s); falling back to CPU", e)
            else:
                log.warning("GPU model %s unavailable (download/cache); trying CPU", model_id)
            self._gpu_disabled = True  # don't re-attempt GPU on every chunk (footer flap)

        # CPU fallback (int8, greedy). "auto" → tiny.en, else the user's choice (which
        # may be slow on CPU — that's their call; the UI flags GPU-oriented models).
        model_id = chosen or CPU_WHISPER_MODEL
        self._emit_engine(f"faster-whisper · loading {model_id}…")
        model_dir = ensure_model(model_id, log)
        if model_dir is None:
            # Both paths failed to get the model on disk — almost always offline with an
            # empty cache. Raise instead of silently re-looping every chunk.
            log.error("CPU model %s unavailable (offline / broken cache)", model_id)
            self._emit_engine("faster-whisper · model unavailable (offline?)")
            raise RuntimeError(f"speech model {model_id} unavailable")
        self.model = WhisperModel(model_dir, device="cpu", compute_type="int8")
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

    def set_paused(self, paused: bool) -> None:
        """Pause/resume capture. Accumulates paused time so chunk timestamps exclude it."""
        if paused and not self._paused:
            self._pause_started = time.time()
        elif not paused and self._paused and self._pause_started is not None:
            self._paused_total += time.time() - self._pause_started
            self._pause_started = None
        self._paused = paused

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


class MediaImportWorker(AudioWorker):
    """Transcribe a local audio/video file in interval-sized segments (batch import).

    An import behaves like a recording compressed in time: the file is split into
    `interval`-second segments and each one becomes a single capture card. For a video,
    a frame is grabbed at the segment start and OCR'd (Tesseract or Gemini vision, exactly
    like a live recording); the segment's audio is transcribed (local Whisper or Gemini).
    Speech + slide text + image all land on the *one* capture for that segment, so the
    transcript is divided the same way recording divides it — not dumped into a single row.

    Transcription reuse: this subclasses `AudioWorker` purely to inherit `_transcribe` /
    `_ensure_model` / `_is_silent` / the `engine_fallback`+`api_error` signals. The whole
    live-capture machinery (`run`/`_capture`/`_consume`/the queue) is replaced by `_process`.
    """

    # One finished capture (frame image + slide OCR + speech) per interval segment.
    capture_ready = pyqtSignal(OCRCapture)
    # processed_seconds, total_seconds — media-time progress (for "M:SS / M:SS" + the bar).
    progress = pyqtSignal(float, float)
    # Emitted when all segments are processed, carrying the transcribed media length so the
    # controller can extend the session length.
    import_finished = pyqtSignal(float)
    # Decoding failed (unsupported/corrupt file). Carries a short message for the UI.
    import_failed = pyqtSignal(str)
    # OCR engine name for the footer (the inherited engine_fallback carries the SPEECH one).
    ocr_engine_fallback = pyqtSignal(str)

    # Frames bigger than this (longest side) are downscaled before OCR + saving, so a 4K
    # video doesn't produce multi-MB slide images or stall Tesseract.
    MAX_FRAME_SIDE = 1600

    def __init__(self, session_id: int, base_dir: str, interval: int, file_path: str, start_time, offset: int, speech_api_key: str = "", speech_model: str = DEFAULT_SPEECH_MODEL, ocr_api_key: str = "", start_offset: float = 0.0) -> None:
        # device is irrelevant for a file import — pass None.
        super().__init__(session_id, base_dir, interval, None, start_time, offset, speech_api_key=speech_api_key, speech_model=speech_model)
        self.file_path = file_path
        self.ocr_api_key = ocr_api_key
        # Media position (seconds) to begin transcribing from — lets the user skip an intro.
        self.start_offset = max(0.0, float(start_offset))
        self._ocr = None

    def run(self) -> None:
        try:
            self._process()
        except Exception as e:
            print(f"[Import] worker error: {e}")
            self.import_failed.emit("Could not process this media file.")

    def _process(self) -> None:
        import av
        from faster_whisper.audio import decode_audio
        from core.ocr import OCRWorker

        # Decode the whole audio track once (PyAV under the hood — handles every common
        # audio AND video container) at the pipeline's native rate.
        try:
            audio = np.asarray(decode_audio(self.file_path, sampling_rate=RECORD_SAMPLE_RATE), dtype=np.float32)
        except Exception as e:
            print(f"[Import] decode failed: {e}")
            self.import_failed.emit("Could not read this media file (unsupported or corrupt).")
            return
        duration = len(audio) / RECORD_SAMPLE_RATE

        # Open the video stream (if any) for per-segment frame grabs. Decoding only
        # keyframes keeps seeking fast and is plenty for slide-style lecture video.
        container = vstream = None
        try:
            container = av.open(self.file_path)
            if container.streams.video:
                vstream = container.streams.video[0]
                vstream.codec_context.skip_frame = "NONKEY"
        except Exception as e:
            print(f"[Import] no video stream: {e}")
            container = vstream = None

        # OCR helper: a non-running OCRWorker (no screen region/hwnd) reused only for its
        # text-extraction + Gemini-vision-cleanup logic. Forward its engine/error signals.
        self._ocr = OCRWorker(self.session_id, self.base_dir, self.interval, None, 1, self.start_time, self.offset, ocr_api_key=self.ocr_api_key)
        self._ocr.engine_fallback.connect(self.ocr_engine_fallback)
        self._ocr.api_error.connect(self.api_error)
        self.ocr_engine_fallback.emit(self._ocr.engine_name)  # announce the starting OCR engine

        frames_per_seg = max(1, int(self.interval * RECORD_SAMPLE_RATE))
        pos = min(len(audio), int(self.start_offset * RECORD_SAMPLE_RATE))
        total = max(0.0, duration - self.start_offset)
        processed = 0.0

        try:
            while pos < len(audio) and self._running:
                # Honour pause without busy-spinning.
                while self._paused and self._running:
                    time.sleep(0.1)
                if not self._running:
                    break

                media_t = pos / RECORD_SAMPLE_RATE
                seg = audio[pos:pos + frames_per_seg]
                # Timeline position within the session (continues after any prior content).
                ts = self.offset + (media_t - self.start_offset)

                speech = ""
                if not self._is_silent(seg):
                    try:
                        speech = self._transcribe(seg, ts)
                    except Exception as e:
                        print(f"[Import] transcribe error: {e}")

                image_name, ocr_text = "", ""
                if vstream is not None:
                    img = self._frame_at(container, vstream, media_t)
                    if img is not None:
                        try:
                            ocr_text = self._ocr._maybe_clean(self._ocr._extract_text(img), img)
                        except Exception as e:
                            print(f"[Import] OCR error: {e}")
                        image_name = self._save_frame(img)

                self.capture_ready.emit(
                    OCRCapture(ts, image_name, ocr_text, None, self.session_id, speech or None)
                )

                pos += frames_per_seg
                processed = min(total, processed + self.interval)
                self.progress.emit(processed, total)
        finally:
            if container is not None:
                container.close()

        self.import_finished.emit(total if self._running else processed)

    def _frame_at(self, container, vstream, t: float):
        """Grab the keyframe at or before media time `t` as a (possibly downscaled) PIL image."""
        try:
            target = int(t / vstream.time_base) + (vstream.start_time or 0)
            container.seek(target, stream=vstream, backward=True, any_frame=False)
            for frame in container.decode(vstream):
                return self._fit_frame(frame.to_image())
        except Exception as e:
            print(f"[Import] frame grab failed at {t:.1f}s: {e}")
        return None

    def _fit_frame(self, pil_img):
        w, h = pil_img.size
        longest = max(w, h)
        if longest > self.MAX_FRAME_SIDE:
            scale = self.MAX_FRAME_SIDE / longest
            from PIL import Image
            pil_img = pil_img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        return pil_img

    def _save_frame(self, pil_img) -> str:
        from datetime import datetime
        from pathlib import Path
        name = "IMP_" + datetime.now().strftime('%y%m%d_%H%M%S.%f')[:-3]
        captures_dir = Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures'
        captures_dir.mkdir(parents=True, exist_ok=True)
        pil_img.save(str(captures_dir / f"{name}.png"))
        return f"{name}.png"
