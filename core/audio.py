import time
import tempfile, os
import sounddevice as sd
import soundfile as sf
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from faster_whisper import WhisperModel

class AudioWorker(QThread):    
    chunk_ready = pyqtSignal(float, str)   
    
    def __init__(self, session_id: int, base_dir: str, interval: int, device, start_time: time, offset: int, speech_api_key: str = "") -> None:
        super().__init__()
        self._running = True
    
        self.session_id = session_id
        self.base_dir = base_dir
        self.interval = interval
        self.speech_api_key = speech_api_key
        
        # Handle device which could be int, dict, or None
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

    def find_loopback_device(self):
        devices = sd.query_devices()
        
        # Look for WASAPI or Stereo Mix devices
        for i, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                name_lower = device["name"].lower()
                if "wasapi" in name_lower or "stereo mix" in name_lower or "loopback" in name_lower:
                    return i
        
        # Try default input device as fallback
        try:
            default = sd.default.device[0]  # input device
            if default is not None:
                print(f"Using default input device as fallback: {default}")
                return default
        except:
            pass
            
        return None

    def _transcribe(self, tmp: str, chunk_start: float) -> str:
        extracted_text = ""
        if self.speech_api_key:
            try:
                extracted_text = self._transcribe_api(tmp, chunk_start)
                if extracted_text:
                    return extracted_text
                print("[Audio] API returned empty, falling back to local...")
            except Exception as e:
                print(f"[Audio] API failed ({e}), falling back to local...")
        return self._transcribe_local(tmp, chunk_start)

    def _transcribe_local(self, tmp: str, chunk_start: float) -> str:
        extracted_text = ""
        try:
            segments, info = self.model.transcribe(tmp, beam_size=5, language="en")
            for segment in segments:
                print(f"[{chunk_start + segment.start:.2f}s -> {chunk_start + segment.end:.2f}s] {segment.text.strip()}\n")
                extracted_text += f"[{chunk_start + segment.start:.2f}s -> {chunk_start + segment.end:.2f}s] {segment.text.strip()}\n"
        except Exception as e:
            print(f"Transcription error: {e}")
        return extracted_text

    def _transcribe_api(self, tmp: str, chunk_start: float) -> str:
        import base64, json, urllib.request, urllib.error
        extracted_text = ""
        with open(tmp, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        payload = json.dumps({
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": 44100,
                "languageCode": "en-US",
                "enableWordTimeOffsets": True,
                "model": "latest_long",
            },
            "audio": {"content": audio_b64}
        }).encode("utf-8")
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={self.speech_api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        for alternative in result.get("results", []):
            words = alternative.get("alternatives", [{}])[0].get("words", [])
            if words:
                t0 = chunk_start + float(words[0]["startTime"].rstrip("s"))
                t1 = chunk_start + float(words[-1]["endTime"].rstrip("s"))
                text = " ".join(w["word"] for w in words)
                line = f"[{t0:.2f}s -> {t1:.2f}s] {text}"
            else:
                text = alternative.get("alternatives", [{}])[0].get("transcript", "").strip()
                line = f"[{chunk_start:.2f}s] {text}"
            if line:
                print(line)
                extracted_text += line + "\n"
        return extracted_text

    def record_loopback(self) -> None:
        chunk_start = time.time() - self.start_time + self.offset
        
        device_id = self.find_loopback_device()
        
        try:
            # Try stereo first (common for system audio)
            audio = sd.rec(
                int(self.interval * 44100), 
                samplerate=44100, 
                channels=2,
                device=device_id,
                dtype='float32'
            )
            sd.wait()
            
            # Convert to mono
            if len(audio.shape) > 1 and audio.shape[1] == 2:
                audio = np.mean(audio, axis=1)
                
        except Exception as e:
            print(f"Loopback stereo failed: {e}, trying mono...")
            try:
                # Fallback to mono
                audio = sd.rec(
                    int(self.interval * 44100), 
                    samplerate=44100, 
                    channels=1,
                    device=device_id,
                    dtype='float32'
                )
                sd.wait()
            except Exception as e2:
                print(f"Loopback mono also failed: {e2}")
                # Final fallback - silent audio
                audio = np.zeros(int(self.interval * 44100))
        
        tmp = tempfile.mktemp(suffix=".wav")
        sf.write(tmp, audio, 44100)
        extracted_text = self._transcribe(tmp, chunk_start)
        timestamp = time.time() - self.start_time + self.offset
        self.chunk_ready.emit(timestamp, extracted_text)
        os.remove(tmp)

    def record_microphone(self) -> None:
        chunk_start = time.time() - self.start_time + self.offset
        
        try:
            audio = sd.rec(
                int(self.interval * 44100), 
                samplerate=44100, 
                channels=1, 
                device=self.device_id
            )
            sd.wait()
        except Exception as e:
            print(f"Microphone error: {e}, trying default device...")
            audio = sd.rec(
                int(self.interval * 44100), 
                samplerate=44100, 
                channels=1, 
                device=None
            )
            sd.wait()
        
        tmp = tempfile.mktemp(suffix=".wav")
        sf.write(tmp, audio, 44100)
        extracted_text = self._transcribe(tmp, chunk_start)
        timestamp = time.time() - self.start_time + self.offset
        self.chunk_ready.emit(timestamp, extracted_text)
        os.remove(tmp)

    def run(self) -> None:
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
        while self._running:
            if self.device_type == "loopback":
                self.record_loopback()
            else:
                self.record_microphone()
        
    def stop(self) -> None:
        self._running = False
        try:
            sd.stop()
        except:
            pass
