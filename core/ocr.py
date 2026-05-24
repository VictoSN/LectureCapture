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
    capture_read = pyqtSignal(OCRCapture)   
    
    def __init__(self, session_id, base_dir, interval, region: dict | None):
        super().__init__()
        self._running = True
    
        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.region = region
        self.previous_text = ""
        self.start_time = None
    
        # Adjust the coordinates with the scaling of the monitor
        if self.region:
            ratio = QApplication.primaryScreen().devicePixelRatio()
            self.region["left"] = int(self.region["left"] * ratio)
            self.region["top"] = int(self.region["top"] * ratio)
            self.region["width"] = int(self.region["width"] * ratio)
            self.region["height"] = int(self.region["height"] * ratio)

        # Ensure the folders exist to avoid FileNotFoundError
        captures_dir = Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures'
        captures_dir.mkdir(parents=True, exist_ok=True)
    
    def compare_text(self, current_text) -> bool:
        ratio = SequenceMatcher(None, current_text, self.previous_text).ratio()
        
        # Only save if its different text
        if ratio >= 0.95:
            return False
        return True
    
    def ocr(self, img):
        pil_img = Image.frombytes("RGB", img.size, img.rgb)

        ## 1. Convert to grayscale
        pil_img = pil_img.convert("L") 
        ## 2. Upscale
        pil_img = pil_img.resize((pil_img.width * 2, pil_img.height *2))
        config = "--psm 6 --oem 3"
        
        return pytesseract.image_to_string(pil_img, config=config)

    def screenshot(self, monitor_index=1):
        with mss.mss() as sct:
            monitor = sct.monitors[monitor_index]
            if not self.region:
                # 0 = All monitors
                # 1 = Main Monitor
                # 2 = Secondary Monitor and etc..
                img = sct.grab(monitor)
            else:
                img = sct.grab(self.region)

            extracted_text = self.ocr(img) # Convert image into text
            
            # Ensure the capture image has different text
            if self.compare_text(extracted_text):
                timestamp = time.time() - self.start_time
                now = datetime.now() # Capture the time for name and date
                name = "OCR_" + now.strftime('%y%m%d_%H%M%S.%f')[:-3]
                full_path = str(Path(self.base_dir) / 'sessions' / str(self.session_id) / 'captures' / f"{name}.png")
                image_path = f"{name}.png"
                self.previous_text = extracted_text # become reference for comparison
                
                # Save to png
                mss.tools.to_png(img.rgb, img.size, output=full_path)
                
                # Store to db and emit signal
                new_capture = OCRCapture(timestamp, image_path, extracted_text, None, self.session_id, None)
                self.capture_read.emit(new_capture)
    
    def run(self):
        self.start_time = time.time()
        while self._running:
            self.screenshot()
            time.sleep(self.interval)
        
    def stop(self):
        self._running = False