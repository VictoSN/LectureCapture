import io
import time
import queue
import threading

import numpy as np

# Import sounddevice/soundfile lazily to avoid PortAudio init cost on startup.

from PyQt6.QtCore import QThread, pyqtSignal

from models.lecture import OCRCapture
from core.worker_common import API_COOLDOWN_SECONDS, RecordingWorkerMixin

RECORD_SAMPLE_RATE = 44100
# faster-whisper wants 16 kHz mono; also reduces API payload size ~5x.
WHISPER_SAMPLE_RATE = 16000
# Caps pending chunks for transcription (bounds memory).
MAX_PENDING_CHUNKS = 5
# Drop silent chunks below this RMS threshold (avoids hallucinated gibberish).
SILENCE_RMS_THRESHOLD = 0.005

# GPU uses distil-large-v3; CPU uses tiny.en. English-only.
CPU_WHISPER_MODEL = "tiny.en"

# Default speech model. Legacy "auto" handled in _ensure_model.
DEFAULT_SPEECH_MODEL = "small.en"


class AudioWorker(RecordingWorkerMixin, QThread):
    chunk_ready = pyqtSignal(float, str)
    # Shows placeholder while a chunk is being transcribed.
    chunk_pending = pyqtSignal(float)
    engine_fallback = pyqtSignal(str)
    # API failure mid-recording status (from core.api_errors).
    api_error = pyqtSignal(str)

    def __init__(self, session_id: int, base_dir: str, interval: int, device, start_time, offset: int, speech_api_key: str = "", speech_model: str = DEFAULT_SPEECH_MODEL, loopback_pid: int | None = None) -> None:
        super().__init__()
        self._running = True

    # Target window PID for WASAPI process loopback. Falls back to system loopback.
        self.loopback_pid = loopback_pid

        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.speech_api_key = speech_api_key
        # Local Whisper model id (e.g. "small.en").
        self.speech_model = speech_model or DEFAULT_SPEECH_MODEL

        # Pause tracking + API-cooldown state shared with OCR worker.
        self._init_worker_common()

        # Lazy-loaded only if local transcription runs.
        self.model = None
        # Footer label: GPU vs CPU.
        self._local_engine_label = "faster-whisper"
        # Stops retrying GPU after failure (avoids model text flapping on every chunk).
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
        # Sample rate for _transcribe; live uses 44100, import uses 16000.
        self.sample_rate = RECORD_SAMPLE_RATE

        # Queue drained by consumer thread so capture never pauses during transcription.
        self._queue: queue.Queue = queue.Queue(maxsize=MAX_PENDING_CHUNKS)
        self._consumer = None

    # Device selection

    def find_loopback_device(self):
        import sounddevice as sd
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                name = device["name"].lower()
                if "wasapi" in name or "stereo mix" in name or "loopback" in name:
                    return i
        # No loopback available; fall back to default mic.
        self.api_error.emit("mic_fallback")
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

    # Capture (producer)

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
        # Process loopback captures only the target window's audio.
        if self.loopback_pid:
            if self._try_process_loopback():
                return
            print("[Audio] process loopback unavailable; using system loopback")

        # System-wide WASAPI loopback captures all system audio output.
        if self.device_type == "loopback":
            if self._try_system_loopback():
                return
            print("[Audio] WASAPI system loopback unavailable; trying sounddevice")

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

    def _try_process_loopback(self) -> bool:
        """Via WASAPI process loopback. Returns True if stream ran, False so caller falls back."""
        from core.process_loopback import ProcessLoopbackRecorder
        recorder = ProcessLoopbackRecorder(self.loopback_pid, samplerate=RECORD_SAMPLE_RATE)
        try:
            recorder.start()
        except Exception as e:
            print(f"[Audio] process loopback start failed for pid={self.loopback_pid}: {e}")
            return False
        print(f"[Audio] capturing process loopback for pid={self.loopback_pid}")
        try:
            self._drain_loopback(recorder)
        except Exception as e:
            print(f"[Audio] process loopback capture error: {e}")
        finally:
            recorder.stop()
        return True

    def _try_system_loopback(self) -> bool:
        """Capture all system audio via WASAPI loopback. Returns True if stream ran."""
        from core.process_loopback import ProcessLoopbackRecorder
        recorder = ProcessLoopbackRecorder(pid=None, samplerate=RECORD_SAMPLE_RATE)
        try:
            recorder.start()
        except Exception as e:
            print(f"[Audio] WASAPI system loopback start failed: {e}")
            return False
        print("[Audio] capturing system-wide WASAPI loopback")
        try:
            self._drain_loopback(recorder)
        except Exception as e:
            print(f"[Audio] system loopback capture error: {e}")
        finally:
            recorder.stop()
        return True

    def _drain_loopback(self, recorder) -> None:
            # Same chunking as _run_stream but from the process-loopback recorder.
        frames_per_chunk = int(self.interval * RECORD_SAMPLE_RATE)
        blocks, blen = [], 0
        while self._running:
            block = recorder.read(timeout=0.2)
            if block is None:
                continue
            # Drop audio captured while paused so the pause isn't transcribed.
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

    def _run_stream(self, device, channels) -> None:
        import sounddevice as sd
        frames_per_chunk = int(self.interval * RECORD_SAMPLE_RATE)
        cb_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            mono = indata.mean(axis=1) if (indata.ndim > 1 and indata.shape[1] > 1) else indata.reshape(-1)
            cb_queue.put(mono.copy())

            # Stream opened and closed on this thread; no cross-thread PortAudio calls.
        with sd.InputStream(samplerate=RECORD_SAMPLE_RATE, channels=channels, device=device, dtype="float32", callback=callback):
            blocks, blen = [], 0
            while self._running:
                try:
                    block = cb_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                # Drop audio captured while paused.
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

    # Transcription (consumer)

    def _consume(self) -> None:
        # Preload and warm the local model so first-chunk latency overlaps recording.
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
            # Attach speech to the slide that was on screen at chunk_start.
            self.chunk_ready.emit(chunk_start, text)

    def _is_silent(self, audio: np.ndarray) -> bool:
        if audio.size == 0:
            return True
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
        return rms < SILENCE_RMS_THRESHOLD

    def _to_16k_array(self, audio: np.ndarray, rate: int = RECORD_SAMPLE_RATE) -> np.ndarray:
        """Resample mono float32 at `rate` down to 16 kHz mono float32."""
        if rate == WHISPER_SAMPLE_RATE:
            return np.asarray(audio, dtype=np.float32)
        n = int(len(audio) * WHISPER_SAMPLE_RATE / rate)
        return np.interp(
            np.linspace(0, len(audio) - 1, n),
            np.arange(len(audio)),
            audio.astype(np.float64),
        ).astype(np.float32)

    def _to_wav_bytes_16k(self, audio: np.ndarray) -> bytes:
        # Resample to 16kHz and encode as WAV. Smaller payload for Gemini API.
        import soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, self._to_16k_array(audio, self.sample_rate), WHISPER_SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"[{m}:{s:02d}]"

    def _transcribe(self, audio: np.ndarray, chunk_start: float) -> str:
        if self._api_available():
            try:
                text, model = self._transcribe_api(self._to_wav_bytes_16k(audio), chunk_start)
                from core.gemini import pretty_model
                self._emit_engine(pretty_model(model))
                return text
            except Exception as e:
                print(f"[Audio] API failed ({e}); using local for ~{API_COOLDOWN_SECONDS}s")
                self._start_api_cooldown()
                from core.api_errors import classify_api_error
                self.api_error.emit(classify_api_error(e))
        text = self._transcribe_local(audio, chunk_start)
        self._emit_engine(self._local_engine_label)
        return text

    def _api_available(self) -> bool:
        return bool(self.speech_api_key) and time.time() >= self._api_cooldown_until

    def _ensure_model(self):
        if self.model is not None:
            return self.model
        from faster_whisper import WhisperModel
        from core.models import ensure_model
        from core.applog import get_logger
        log = get_logger()

        # Honour the chosen model on the available device; legacy "auto" resolves per-device below.
        chosen = self.speech_model if self.speech_model != "auto" else None

        # Prefer GPU for large models; fall back to CPU if CUDA fails.
        from core.cuda_setup import prepare_cuda
        if prepare_cuda() and not self._gpu_disabled:
            # "Automatic" → best model for the detected GPU's VRAM.
            from core.hardware import auto_gpu_model
            model_id = chosen or auto_gpu_model()
            self._emit_engine(f"faster-whisper · loading {model_id}…")
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

        # CPU fallback (int8, greedy).
        model_id = chosen or CPU_WHISPER_MODEL
        self._emit_engine(f"faster-whisper · loading {model_id}…")
        model_dir = ensure_model(model_id, log)
        if model_dir is None:
            # Both paths failed. Usually offline with empty cache.
            log.error("CPU model %s unavailable (offline / broken cache)", model_id)
            self._emit_engine("faster-whisper · model unavailable (offline?)")
            raise RuntimeError(f"speech model {model_id} unavailable")
        self.model = WhisperModel(model_dir, device="cpu", compute_type="int8")
        self._local_engine_label = f"faster-whisper · {model_id} · CPU"
        self._emit_engine(self._local_engine_label)
        return self.model

    def _warmup(self, model) -> None:
        # Quick CUDA warmup so the first chunk doesn't pay JIT cost.
        dummy = (np.random.randn(WHISPER_SAMPLE_RATE // 4).astype(np.float32)) * 0.01
        list(model.transcribe(dummy, beam_size=1, language="en")[0])

    def _transcribe_local(self, audio: np.ndarray, chunk_start: float) -> str:
        try:
            model = self._ensure_model()
            # Feed 16 kHz float32 directly (no WAV round-trip). vad_filter guards against hallucination.
            segments, _info = model.transcribe(
                self._to_16k_array(audio, self.sample_rate), beam_size=1, language="en", vad_filter=True
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
        # Drain pending chunks for a quick shutdown; the capture loop closes its own stream via _running.
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
    """Transcribe a local media file into interval-sized capture cards."""

    capture_ready = pyqtSignal(OCRCapture)  # One capture card per segment.
    progress = pyqtSignal(float, float)  # processed_s, total_s
    import_finished = pyqtSignal(float)  # transcribed length
    import_failed = pyqtSignal(str)  # decode error
    ocr_engine_fallback = pyqtSignal(str)  # OCR engine name for footer

    # Downscale frames larger than this before OCR (avoids multi-MB slide images).
    MAX_FRAME_SIDE = 1600

    def __init__(self, session_id: int, base_dir: str, interval: int, file_path: str, start_time, offset: int, speech_api_key: str = "", speech_model: str = DEFAULT_SPEECH_MODEL, ocr_api_key: str = "", start_offset: float = 0.0) -> None:
        # device is irrelevant for a file import. Pass None.
        super().__init__(session_id, base_dir, interval, None, start_time, offset, speech_api_key=speech_api_key, speech_model=speech_model)
        # Decode audio at 16 kHz (~2.75× less RAM than 44.1 kHz).
        self.sample_rate = WHISPER_SAMPLE_RATE
        self.file_path = file_path
        self.ocr_api_key = ocr_api_key
        # Media position (seconds) to begin transcribing from. Lets the user skip an intro.
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

        # Decode the whole audio track once at the transcription rate.
        try:
            audio = np.asarray(decode_audio(self.file_path, sampling_rate=self.sample_rate), dtype=np.float32)
        except Exception as e:
            print(f"[Import] decode failed: {e}")
            self.import_failed.emit("Could not read this media file (unsupported or corrupt).")
            return
        duration = len(audio) / self.sample_rate

        # Video stream for per-segment frame grabs. Keyframes only (fast, enough for slides).
        container = vstream = None
        try:
            container = av.open(self.file_path)
            if container.streams.video:
                vstream = container.streams.video[0]
                vstream.codec_context.skip_frame = "NONKEY"
        except Exception as e:
            print(f"[Import] no video stream: {e}")
            container = vstream = None

        # Non-running OCRWorker reused for text extraction and Gemini cleanup.
        self._ocr = OCRWorker(self.session_id, self.base_dir, self.interval, None, 1, self.start_time, self.offset, ocr_api_key=self.ocr_api_key)
        self._ocr.engine_fallback.connect(self.ocr_engine_fallback)
        self._ocr.api_error.connect(self.api_error)
        self.ocr_engine_fallback.emit(self._ocr.engine_name)  # announce the starting OCR engine

        frames_per_seg = max(1, int(self.interval * self.sample_rate))
        pos = min(len(audio), int(self.start_offset * self.sample_rate))
        total = max(0.0, duration - self.start_offset)
        processed = 0.0

        try:
            while pos < len(audio) and self._running:
                # Honour pause without busy-spinning.
                while self._paused and self._running:
                    time.sleep(0.1)
                if not self._running:
                    break

                media_t = pos / self.sample_rate
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
