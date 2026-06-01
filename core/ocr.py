import pytesseract
import mss, mss.tools
import time

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal

from models.lecture import OCRCapture

from PIL import Image
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

class OCRWorker(QThread):    
    capture_ready = pyqtSignal(OCRCapture)   
    
    def __init__(self, session_id, base_dir, interval, region: dict | None, monitor_index, start_time, offset, hwnd=None) -> None:
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
    
        self.sct = mss.mss()
    
        # Adjust the coordinates with the scaling of the monitor
        if self.region:
            monitor = self.sct.monitors[self.monitor_index]
            screens = QApplication.screens()
            ratio = 1.0
            
            # Get ratio per monitor
            for screen in screens:
                sg = screen.geometry()
                if sg.x() == monitor["left"] and sg.y() == monitor["top"]:
                    ratio = screen.devicePixelRatio()
                    break
                
            self.region["left"] = int((self.region["left"] + monitor["left"]) * ratio)
            self.region["top"] = int((self.region["top"] + monitor["top"]) * ratio)
            self.region["width"] = min(int(self.region["width"] * ratio), monitor["width"])
            self.region["height"] = min(int(self.region["height"] * ratio), monitor["height"])
    
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
        pil_img = pil_img.convert("L")
        pil_img = pil_img.resize((pil_img.width * 2, pil_img.height * 2))
        config = "--psm 6 --oem 3"
        return pytesseract.image_to_string(pil_img, config=config)
    
    def get_window_screenshot(self):
        import win32gui
        import win32ui
        from ctypes import windll
        
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            return None
        
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        width = right - left
        height = bottom - top
        
        hwnd_dc = win32gui.GetWindowDC(self.hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)
        
        windll.user32.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 3)
        
        bmp_info = bitmap.GetInfo()
        bmp_bits = bitmap.GetBitmapBits(True)
        pil_img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]), bmp_bits, "raw", "BGRX")
        
        # Cleanup
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, hwnd_dc)
        win32gui.DeleteObject(bitmap.GetHandle())
        
        return pil_img
    
    def run(self) -> None:
        while self._running:
            self.screenshot()
            
            # Due to using '.wait' in MainWindow, the thread will only close at interval time
            # Make interval 1/10th as fast, to be able to close it in time.
            for _ in range(self.interval * 10):
                if not self._running:
                    break
                time.sleep(0.1)
        
    def stop(self) -> None:
        self._running = False