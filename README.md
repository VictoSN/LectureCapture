# LectureCapture
Final Year Project that uses python to create an automatic transcript for visual and audio materials in online meeting platforms

## How to run (Windows Only)
1. Clone the repo
2. Create a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```
3. Install dependencies:
```bash
pip install PyQt6 PyQt6-Frameless-Window numpy pytesseract Pillow mss sounddevice soundfile faster_whisper sumy pywin32 google-genai
```
4. (Optional) For GPU-accelerated speech transcription on an NVIDIA GPU, also install the CUDA 12 runtime. Without these, transcription falls back to the CPU:
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```
5. Install Tesseract (the OCR engine `pytesseract` calls): download and run the Windows installer from https://github.com/UB-Mannheim/tesseract/wiki
6. Run:
```bash
python main.py
```

## License
This project is licensed under the [MIT License](LICENSE)