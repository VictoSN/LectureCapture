import time
import tempfile, os
import sounddevice as sd
import soundfile as sf
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from faster_whisper import WhisperModel

class AudioWorker(QThread):    
    chunk_ready = pyqtSignal(float, str)   
    
    def __init__(self, session_id, base_dir, interval, start_time, offset) -> None:
        super().__init__()
        self._running = True
    
        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.start_time = start_time        
        self.offset = offset

    def record(self) -> None:
        chunk_start = time.time() - self.start_time + self.offset # get start time for each chunk
        
        # Start recording
        audio = sd.rec(int(self.interval * 44100), samplerate=44100, channels=1)
        sd.wait() # blocks until the recording is done
        
        tmp = tempfile.mktemp(suffix=".wav") # Create temp wav file
        sf.write(tmp, audio, 44100) # Save to temp file
        
        # Get speech-to-text using whisper
        extracted_text = ""
        segments, info = self.model.transcribe(tmp, beam_size=5, language="en")
        print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
        for segment in segments:
            print(f"[{chunk_start + segment.start:.2f}s -> {chunk_start + segment.end:.2f}s] {segment.text.strip()}\n")
            extracted_text += f"[{chunk_start + segment.start:.2f}s -> {chunk_start + segment.end:.2f}s] {segment.text.strip()}\n"
        timestamp = time.time() - self.start_time + self.offset # Time stamp for the transcript

        self.chunk_ready.emit(timestamp, extracted_text)
        os.remove(tmp) # Delete temp file

    def run(self) -> None:
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
        while self._running:
            self.record()
        
    def stop(self) -> None:
        self._running = False
        sd.stop()
