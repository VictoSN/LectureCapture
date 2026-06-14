import re
import time
import pytesseract
import mss, mss.tools
import win32gui
import numpy as np

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal

from models.lecture import OCRCapture

from PIL import Image
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

# After an API failure (e.g. a rate limit) stop calling the API for this long
# before trying again, so a transient 429 doesn't permanently disable cleanup.
API_COOLDOWN_SECONDS = 60

# --- slide-change detection (dedup) tuning --------------------------------
# A capture is saved only when the slide actually changes. The OCR text is the
# authority (so a moving cursor/webcam/clock in frame doesn't create duplicates);
# a perceptual image hash provides a cheap "definitely identical" fast path and a
# fallback for slides that contain no text (diagrams, photos).
AHASH_SIZE = 16                 # hash is AHASH_SIZE*AHASH_SIZE bits
AHASH_IDENTICAL = 1             # <= this many differing bits => same image, skip OCR
IMAGE_HAMMING_THRESHOLD = 12    # for text-less slides: new slide if more bits differ
TEXT_SIMILARITY = 0.90          # new slide if normalized text similarity drops below this
BLANK_STD_THRESHOLD = 8         # ignore near-uniform, text-less frames (e.g. a blank screen)
# Only compare this fraction of tokens for slide identity. Dynamic elements like
# live poll counts, timers, and vote tallies sit at the bottom of slides and
# change every few seconds — comparing only the head (title + main content) stops
# them from triggering duplicate captures.
HEAD_FRACTION = 0.6

# Set True to log why each frame was captured/skipped (helps diagnose/tune dedup).
DEBUG_DEDUP = False


class OCRWorker(QThread):
    capture_ready = pyqtSignal(OCRCapture)
    engine_fallback = pyqtSignal(str)

    def __init__(self, session_id, base_dir, interval, region: dict | None, monitor_index, start_time, offset, hwnd=None, ocr_api_key: str = "") -> None:
        super().__init__()
        self._running = True
        self._force = False

        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.region = region
        self.monitor_index = monitor_index or 1
        self.start_time = start_time
        self.offset = offset
        self.hwnd = hwnd
        self.ocr_api_key = ocr_api_key

        # Slide-change detection state — the last SAVED slide's image hash, the last
        # frame's Tesseract text (cheap pre-filter), and the last SAVED vision text
        # (authoritative post-filter: the text we actually show the user).
        self.previous_raw = ""
        self.previous_saved = ""
        self.previous_ahash = None

        # API fallback state — cooldown-based instead of permanently sticky.
        self._api_cooldown_until = 0.0
        self._last_engine = self.engine_name

        # mss is NOT thread-safe: the grabbing instance is created in run() on the
        # worker thread. Here we only need monitor geometry for a one-off
        # coordinate conversion, so use a short-lived instance on this thread.
        self.sct = None

        if not self.hwnd and self.region:
            # 'region' arrives as absolute logical screen coordinates from the
            # overlay. Convert to physical pixels relative to the monitor so that
            # mss.grab() (physical pixel coords relative to each monitor) gets the
            # right rectangle.
            with mss.mss() as sct:
                monitor = sct.monitors[self.monitor_index]
                ratio = 1.0
                for screen in QApplication.screens():
                    sg = screen.geometry()
                    phys_x = int(sg.x() * screen.devicePixelRatio())
                    phys_y = int(sg.y() * screen.devicePixelRatio())
                    if phys_x == monitor["left"] and phys_y == monitor["top"]:
                        ratio = screen.devicePixelRatio()
                        break

                monitor_logical_left = monitor["left"] // ratio
                monitor_logical_top = monitor["top"] // ratio

                rel_left = self.region["left"] - monitor_logical_left
                rel_top = self.region["top"] - monitor_logical_top

                self.region = {
                    "left":   monitor["left"] + int(rel_left * ratio),
                    "top":    monitor["top"]  + int(rel_top  * ratio),
                    "width":  min(int(self.region["width"]  * ratio), monitor["width"]),
                    "height": min(int(self.region["height"] * ratio), monitor["height"]),
                }

        # For hwnd captures, store the crop box (logical pixels within the window).
        # When region is None the full window is captured.
        self.crop_box = None
        if self.hwnd and self.region:
            self.crop_box = (
                self.region["left"],
                self.region["top"],
                self.region["left"] + self.region["width"],
                self.region["top"]  + self.region["height"],
            )

        # Ensure the folders exist to avoid FileNotFoundError
        captures_dir = Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures'
        captures_dir.mkdir(parents=True, exist_ok=True)

    # ---- capture + slide-change detection ------------------------------

    def screenshot(self, force: bool = False) -> None:
        t0 = time.time()
        pil_img = self._grab_pil()
        if pil_img is None:
            return
        t1 = time.time()
        print(f"[OCR timing] grab:    {t1-t0:.3f}s")

        gray = self._downscale_gray(pil_img)
        ahash = gray > gray.mean()
        img_dist = self._hamming(ahash, self.previous_ahash) if self.previous_ahash is not None else -1

        # Fast path: a near-identical image is certainly the same slide still on
        # screen — skip the (expensive) OCR entirely. `force` ("Capture Now")
        # bypasses all dedup.
        if not force and self.previous_ahash is not None and img_dist <= AHASH_IDENTICAL:
            if DEBUG_DEDUP:
                print(f"[OCR dedup] img_dist={img_dist} -> SKIP (image identical)")
            print(f"[OCR timing] skipped (identical image) total: {time.time()-t0:.3f}s")
            return

        raw_text = self._extract_text(pil_img)
        t2 = time.time()
        print(f"[OCR timing] tesseract: {t2-t1:.3f}s  chars={len(raw_text.strip())}")
        norm = self._normalize(raw_text)

        # Blank frame (e.g. screen blanked to black): no text + near-uniform image.
        # Ignore it and DON'T update state, so the real slide isn't re-captured when
        # it comes back.
        if not force and not norm and float(gray.std()) < BLANK_STD_THRESHOLD:
            if DEBUG_DEDUP:
                print(f"[OCR dedup] std={gray.std():.1f} chars=0 -> SKIP (blank frame)")
            print(f"[OCR timing] skipped (blank frame) total: {time.time()-t0:.3f}s")
            return

        # Decide whether the slide changed. Text is the authority when present;
        # otherwise fall back to the image hash (text-less slides like diagrams).
        if self.previous_ahash is None:
            text_ratio, is_new = 1.0, True
        elif norm:
            text_ratio = self._text_similarity(norm, self.previous_raw)
            is_new = text_ratio < TEXT_SIMILARITY
        else:
            text_ratio, is_new = -1.0, img_dist > IMAGE_HAMMING_THRESHOLD

        if DEBUG_DEDUP:
            print(f"[OCR dedup] img_dist={img_dist} text_ratio={text_ratio:.2f} "
                  f"chars={len(norm)} -> {'CAPTURE' if (force or is_new) else 'SKIP'} :: {norm[:60]!r}")

        if not force and not is_new:
            print(f"[OCR timing] skipped (same slide) total: {time.time()-t0:.3f}s")
            return

        # New slide *by the cheap Tesseract/image signal*. Run vision OCR (the text we
        # actually save) only now. Tesseract's text above is only used for dedup; the
        # saved text comes from the vision model so math notation is captured.
        text = self._maybe_clean(raw_text, pil_img)
        t3 = time.time()
        print(f"[OCR timing] cleanup: {t3-t2:.3f}s")

        # Mark this frame as seen so the image fast-path can skip its repeats.
        self.previous_raw = norm
        self.previous_ahash = ahash

        # Second safeguard, on the AUTHORITATIVE saved text: Tesseract jitters on noisy
        # frames (animated social embeds, video) and can flag a "new slide" that the
        # vision model transcribes identically to the last save. The vision text is what
        # the user sees, so identical wording must skip here even if Tesseract disagreed.
        saved_norm = self._normalize(text)
        if (not force and self.previous_saved and saved_norm
                and self._text_similarity(saved_norm, self.previous_saved) >= TEXT_SIMILARITY):
            if DEBUG_DEDUP:
                print(f"[OCR dedup] vision text == last save -> SKIP :: {saved_norm[:60]!r}")
            print(f"[OCR timing] skipped (same saved text) total: {time.time()-t0:.3f}s")
            return

        self.previous_saved = saved_norm
        self._save_capture(text, pil_img)
        print(f"[OCR timing] save+emit: {time.time()-t3:.3f}s  TOTAL: {time.time()-t0:.3f}s")

    def _grab_pil(self):
        if self.hwnd:
            pil_img = self.get_window_screenshot()
            if pil_img is None:
                return None
            if self.crop_box:
                pil_img = pil_img.crop(self.crop_box)
            return pil_img

        img = self.sct.grab(self.sct.monitors[self.monitor_index]) if not self.region else self.sct.grab(self.region)
        return Image.frombytes("RGB", img.size, img.rgb)

    def _normalize(self, text: str) -> str:
        # Lowercase, keep only alphanumeric tokens separated by single spaces.
        # Makes the comparison robust to OCR flicker in punctuation/whitespace.
        return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())

    def _text_similarity(self, a: str, b: str) -> float:
        # Compare only the leading HEAD_FRACTION of tokens so dynamic elements at the
        # bottom of a slide (live poll counts, vote tallies, timers, animated embeds)
        # don't make an otherwise-identical slide look new. Inputs must be normalized.
        tokens_a, tokens_b = a.split(), b.split()
        n = max(20, int(max(len(tokens_a), len(tokens_b)) * HEAD_FRACTION))
        head_a = " ".join(tokens_a[:n])
        head_b = " ".join(tokens_b[:n])
        return SequenceMatcher(None, head_a, head_b).ratio()

    def _downscale_gray(self, pil_img):
        small = pil_img.convert("L").resize((AHASH_SIZE, AHASH_SIZE), Image.BILINEAR)
        return np.asarray(small, dtype=np.float32)

    def _hamming(self, a, b) -> int:
        return int(np.count_nonzero(a != b))

    def _extract_text(self, pil_img) -> str:
        from PIL import ImageFilter, ImageEnhance
        gray = pil_img.convert("L")
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
        gray = ImageEnhance.Contrast(gray).enhance(2.0)
        gray = gray.filter(ImageFilter.SHARPEN)
        return pytesseract.image_to_string(gray, config="--psm 6 --oem 3")

    def _save_capture(self, text: str, pil_img) -> None:
        timestamp = time.time() - self.start_time + self.offset
        name = "OCR_" + datetime.now().strftime('%y%m%d_%H%M%S.%f')[:-3]
        full_path = str(Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures' / f"{name}.png")
        pil_img.save(full_path)
        capture = OCRCapture(timestamp, f"{name}.png", text, None, self.session_id, None)
        self.capture_ready.emit(capture)

    # ---- API cleanup ---------------------------------------------------

    def _maybe_clean(self, raw_text: str, pil_img) -> str:
        # When the API is available, transcribe the IMAGE directly with the vision
        # model so math notation (∈, ⊕, ℕ, etc.) is captured — Tesseract can't read
        # it. Note: we deliberately don't early-return on empty raw_text, because a
        # math-only slide can produce no Tesseract text yet still need OCR.
        if self._api_available():
            try:
                text = self._ocr_with_api(pil_img)
                if text.strip():
                    self._emit_engine("gemini vision")
                    return text
                # Empty vision result — fall back to whatever Tesseract gave us.
            except Exception as e:
                print(f"[OCR] API OCR failed ({e}); using raw text, cooldown {API_COOLDOWN_SECONDS}s")
                self._api_cooldown_until = time.time() + API_COOLDOWN_SECONDS
                self._emit_engine("pytesseract")
        return raw_text

    def _api_available(self) -> bool:
        return bool(self.ocr_api_key) and time.time() >= self._api_cooldown_until

    def _emit_engine(self, name: str) -> None:
        if name != self._last_engine:
            self._last_engine = name
            self.engine_fallback.emit(name)

    def _ocr_with_api(self, pil_img) -> str:
        from google import genai
        client = genai.Client(api_key=self.ocr_api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=[
                (
                    "Transcribe ALL text from this lecture slide exactly as it appears, "
                    "preserving the reading order, structure, and line breaks. "
                    "Render every mathematical expression, symbol, equation, or formula in "
                    "LaTeX: wrap inline math in $...$ and display equations in $$...$$. "
                    "Use proper LaTeX commands for symbols (e.g. \\in, \\bigoplus, "
                    "\\mathbb{N}, \\mathcal{AT}, subscripts G_n). "
                    "Do not add commentary, headings, or explanations — return only the "
                    "transcribed slide content."
                ),
                pil_img,
            ],
        )
        return response.text or ""

    @property
    def engine_name(self) -> str:
        return "gemini vision" if self.ocr_api_key else "pytesseract"

    # ---- window screenshot --------------------------------------------

    def get_window_screenshot(self):
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            return None
        return OCRWorker.get_window_screenshot_static(self.hwnd)

    @staticmethod
    def get_window_screenshot_static(hwnd) -> "Image":
        import win32ui
        from ctypes import windll

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            return None

        hwnd_dc = mfc_dc = save_dc = bitmap = None
        try:
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)
            windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)
            bmp_info = bitmap.GetInfo()
            bmp_bits = bitmap.GetBitmapBits(True)
            return Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]), bmp_bits, "raw", "BGRX")
        finally:
            # Always release GDI objects, even if PrintWindow raises — otherwise
            # handles leak every interval until Windows refuses to create more.
            if save_dc:
                save_dc.DeleteDC()
            if mfc_dc:
                mfc_dc.DeleteDC()
            if hwnd_dc:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
            if bitmap:
                win32gui.DeleteObject(bitmap.GetHandle())

    # ---- worker loop ---------------------------------------------------

    def run(self) -> None:
        self._force = False
        try:
            # Create the mss instance on THIS (the worker) thread and keep it here.
            with mss.mss() as self.sct:
                while self._running:
                    start = time.time()
                    forced = self._force
                    self._force = False
                    try:
                        self.screenshot(force=forced)
                    except Exception as e:
                        print(f"[OCR] capture error: {e}")

                    # Sleep the remainder of the interval, staying responsive to
                    # stop() and force_capture() (checked every 100ms).
                    remaining = self.interval - (time.time() - start)
                    while remaining > 0 and self._running and not self._force:
                        time.sleep(min(0.1, remaining))
                        remaining -= 0.1
        except Exception as e:
            print(f"[OCR] worker stopped unexpectedly: {e}")

    def force_capture(self) -> None:
        """Trigger an immediate screenshot and reset the interval countdown."""
        self._force = True

    def stop(self) -> None:
        self._running = False
