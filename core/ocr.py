import pytesseract
import mss, mss.tools
import time
import win32gui

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal

from models.lecture import OCRCapture

from PIL import Image
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

class OCRWorker(QThread):    
    capture_ready = pyqtSignal(OCRCapture)
    engine_fallback = pyqtSignal(str)
    
    def __init__(self, session_id, base_dir, interval, region: dict | None, monitor_index, start_time, offset, hwnd=None, ocr_api_key: str = "") -> None:
        super().__init__()
        self._running = True
    
        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.region = region
        self.monitor_index = monitor_index or 1
        self.start_time = start_time
        self.offset = offset
        self.hwnd = hwnd
        self.previous_text = ""
        self.ocr_api_key = ocr_api_key
        self._api_failed = False
    
        self.sct = mss.mss()

        if not self.hwnd and self.region:
            # 'region' arrives as absolute logical screen coordinates from the overlay.
            # Convert to physical pixels and make them relative to the monitor so that
            # mss.grab() (which always uses physical pixel coords relative to each
            # monitor) gets the right rectangle.
            monitor = self.sct.monitors[self.monitor_index]
            screens = QApplication.screens()
            ratio = 1.0

            for screen in screens:
                sg = screen.geometry()
                phys_x = int(sg.x() * screen.devicePixelRatio())
                phys_y = int(sg.y() * screen.devicePixelRatio())
                if phys_x == monitor["left"] and phys_y == monitor["top"]:
                    ratio = screen.devicePixelRatio()
                    break

            # Subtract the monitor's logical origin first, then scale to physical pixels.
            monitor_logical_left = monitor["left"] // ratio  # logical origin of this monitor
            monitor_logical_top  = monitor["top"]  // ratio

            rel_left = self.region["left"] - monitor_logical_left
            rel_top  = self.region["top"]  - monitor_logical_top

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
    
    def compare_text(self, current_text) -> bool:
        ratio = SequenceMatcher(None, current_text, self.previous_text).ratio()
        
        # Only save if its different text
        if ratio >= 0.95:
            return False
        return True
    
    def ocr(self, img) -> str:
        pil_img = Image.frombytes("RGB", img.size, img.rgb)
        return self.ocr_pil(pil_img)

    def screenshot(self) -> None:        
        if self.hwnd:
            pil_img = self.get_window_screenshot()
            if pil_img is None:
                return

            # Crop to the user-selected region if one was provided
            if self.crop_box:
                pil_img = pil_img.crop(self.crop_box)

            extracted_text = self.ocr_pil(pil_img)
            
            if self.compare_text(extracted_text):
                timestamp = time.time() - self.start_time + self.offset
                now = datetime.now()
                name = "OCR_" + now.strftime('%y%m%d_%H%M%S.%f')[:-3]
                full_path = str(Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures' / f"{name}.png")
                image_path = f"{name}.png"
                self.previous_text = extracted_text
                
                pil_img.save(full_path)  # PIL save directly
                
                new_capture = OCRCapture(timestamp, image_path, extracted_text, None, self.session_id, None)
                self.capture_ready.emit(new_capture)
        else:
            img = self.sct.grab(self.sct.monitors[self.monitor_index]) if not self.region else self.sct.grab(self.region)
            extracted_text = self.ocr(img)
            
            if self.compare_text(extracted_text):
                timestamp = time.time() - self.start_time + self.offset
                now = datetime.now()
                name = "OCR_" + now.strftime('%y%m%d_%H%M%S.%f')[:-3]
                full_path = str(Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures' / f"{name}.png")
                image_path = f"{name}.png"
                self.previous_text = extracted_text
                
                mss.tools.to_png(img.rgb, img.size, output=full_path)
                
                new_capture = OCRCapture(timestamp, image_path, extracted_text, None, self.session_id, None)
                self.capture_ready.emit(new_capture)
            
    def ocr_pil(self, pil_img) -> str:
        from PIL import ImageFilter, ImageEnhance
        pil_img = pil_img.convert("L")
        pil_img = pil_img.resize((pil_img.width * 2, pil_img.height * 2), Image.LANCZOS)
        pil_img = ImageEnhance.Contrast(pil_img).enhance(2.0)
        pil_img = pil_img.filter(ImageFilter.SHARPEN)
        config = "--psm 6 --oem 3"
        raw_text = pytesseract.image_to_string(pil_img, config=config)

        if not raw_text.strip():
            return raw_text

        if self.ocr_api_key and not self._api_failed:
            similar = SequenceMatcher(None, raw_text, self.previous_text).ratio() >= 0.95
            if not similar:
                try:
                    return self._cleanup_with_api(raw_text)
                except Exception as e:
                    print(f"[OCR] API cleanup failed, using raw text: {e}")
                    self._mark_api_failed()
        return raw_text

    def _mark_api_failed(self) -> None:
        if not self._api_failed:
            self._api_failed = True
            self.engine_fallback.emit(self.engine_name)

    def _cleanup_with_api(self, raw_text: str) -> str:
        from google import genai
        client = genai.Client(api_key=self.ocr_api_key)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=(
                "The following text was extracted from a lecture slide via OCR and may contain "
                "errors, garbled characters, or broken formatting. Fix any OCR errors and clean up "
                "the text while preserving ALL original content, structure, and meaning. "
                "Return only the cleaned text with no commentary.\n\n"
                f"{raw_text}"
            )
        )
        return response.text

    @property
    def engine_name(self) -> str:
        if self.ocr_api_key and not self._api_failed:
            return "tesseract + gemini"
        return "pytesseract"
    
    def get_window_screenshot(self):
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            return None
        return OCRWorker.get_window_screenshot_static(self.hwnd)
    
    @staticmethod
    def get_window_screenshot_static(hwnd) -> "Image":
        import win32gui, win32ui
        from ctypes import windll
        from PIL import Image

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)
        windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)
        bmp_info = bitmap.GetInfo()
        bmp_bits = bitmap.GetBitmapBits(True)
        pil_img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]), bmp_bits, "raw", "BGRX")

        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        win32gui.DeleteObject(bitmap.GetHandle())
        return pil_img
    
    def run(self) -> None:
        self._force = False
        while self._running:
            self.screenshot()
            
            # Due to using '.wait' in MainWindow, the thread will only close at interval time
            # Make interval 1/10th as fast, to be able to close it in time.
            for _ in range(self.interval * 10):
                if not self._running or self._force:
                    break
                time.sleep(0.1)
            self._force = False

    def force_capture(self) -> None:
        """Trigger an immediate screenshot and reset the interval countdown."""
        self._force = True
        
    def stop(self) -> None:
        self._running = False