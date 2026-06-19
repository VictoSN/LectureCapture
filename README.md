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

## Building a standalone .exe (Windows)
Bundles the app + all dependencies into a self-contained folder, so it runs without Python installed. Whisper speech models are **not** bundled — they download on first use.

1. Install PyInstaller into the venv:
```bash
pip install pyinstaller
```
2. Build (one-folder) using the included spec:
```bash
venv\Scripts\pyinstaller.exe --noconfirm LectureCapture.spec
```
The runnable app is `dist\LectureCapture\` — `LectureCapture.exe` plus its `_internal\` folder. To share it, zip that whole folder (the .exe needs `_internal\` beside it).

Notes:
- `LectureCapture.spec` bundles the NVIDIA CUDA runtime (for GPU transcription) and Tesseract (for local OCR), so the build is large (~2.5 GB) and the machine you build on must have both installed.
- The spec's `CONSOLE` flag is `False` (windowed). Set it to `True` temporarily to see tracebacks/logs while debugging a build.

## Creating an installer (optional)
Wraps the build into a single `setup.exe` (installs to Program Files, adds shortcuts + an uninstaller). Uses [Inno Setup](https://jrsoftware.org/isdl.php):

1. Install Inno Setup (e.g. `winget install JRSoftware.InnoSetup`).
2. Build the .exe first (above), then compile the installer:
```bash
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```
The result is `installer\LectureCapture-Setup.exe`.

## License
This project is licensed under the [MIT License](LICENSE)