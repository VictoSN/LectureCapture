# LectureCapture

LectureCapture is a Windows desktop app that turns an online lecture or meeting into searchable, structured notes. While you watch, it periodically captures the on-screen slides and the audio, reads the slides with OCR, transcribes the speech, and lines each spoken passage up with the slide that was showing at the time. From there it can generate an AI summary and a self-test quiz, and translate or define any selected text on demand.

> Final Year Project — built with Python and PyQt6.

## Features
- **Screen + audio capture** of a screen region, a single window, or a whole monitor, at a configurable interval.
- **Slide OCR** — reads text (and math, as LaTeX) from each captured slide, locally with Tesseract or via Google Gemini vision.
- **Speech-to-text** — local, GPU-accelerated `faster-whisper`, or Gemini; English Whisper models from `tiny` up to `large`.
- **Aligned transcript** — every spoken chunk is attached to the slide that was on screen when it was said.
- **AI summary** — Gemini-generated Markdown notes, with a local `sumy` fallback when no API key is set.
- **Quiz** — auto-generated multiple-choice + true/false questions from the session content, graded automatically.
- **Translate / Define** — right-click any selected text for an instant Gemini lookup.
- **Local-first or API** — run everything on-device (private, no internet) or send chosen steps to Gemini for higher accuracy, with per-engine toggles.
- **Sessions** organised by category/group, searchable, with editable transcripts; plus light/dark themes, keyboard shortcuts, and an in-app help guide.

## Download
Prebuilt Windows installer: **[Releases](https://github.com/VictoSN/LectureCapture/releases/latest)** → `LectureCapture-Setup.exe`. Run it, then launch from the Start Menu.

- GPU speech transcription needs an NVIDIA GPU; it falls back to the CPU otherwise.
- Speech models download automatically the first time you use them (needs internet once).
- Gemini features (Translate/Define, Quiz, and any API-mode step) need a free [Google Gemini API key](https://aistudio.google.com).

## How it works
1. **Capture** — `mss` grabs slide snapshots on an interval and `sounddevice` records the audio in chunks. Each runs on its own worker thread so the UI stays responsive.
2. **OCR** — each slide image is read by `pytesseract` (local) or Gemini vision (API), preserving layout and rendering equations as LaTeX.
3. **Speech** — audio chunks are transcribed by `faster-whisper` (via CTranslate2, GPU through the CUDA runtime) or by Gemini.
4. **Alignment** — each transcript chunk is matched by timestamp to the most recent slide capture, so the slides and narration stay in sync.
5. **Storage** — sessions, captures and transcripts live in a local SQLite database (under `%APPDATA%`), with slide images on disk.
6. **AI** — summary, quiz and translate/define call Gemini through a model-fallback chain (if one model is rate-limited it tries the next); the summary falls back to on-device `sumy`.

The app is **local-first**: with no API key it does OCR, transcription and summaries entirely on your machine.

## Tech stack
| Area | Library |
|---|---|
| GUI | PyQt6, PyQt6-Frameless-Window |
| Screen capture | mss |
| Audio | sounddevice, soundfile |
| Local OCR | pytesseract (+ the Tesseract-OCR engine) |
| Local speech-to-text | faster-whisper (CTranslate2); CUDA 12 runtime (nvidia-cublas-cu12 / nvidia-cudnn-cu12) for GPU |
| Local summary | sumy (+ nltk) |
| Cloud AI | google-genai (Google Gemini — OCR vision, speech, summary, quiz, translate/define) |
| Imaging / math | Pillow, numpy |
| Windows integration | pywin32 |
| Storage | SQLite (Python standard library) |
| Packaging | PyInstaller, Inno Setup |

## How to run from source (Windows only)
1. Clone the repo
2. Create a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```
3. Install dependencies:
```bash
pip install PyQt6 PyQt6-Frameless-Window numpy pytesseract Pillow mss sounddevice soundfile faster_whisper sumy pywin32 google-genai pylatexenc
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

**PowerShell / Windows Terminal**
```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

**Command Prompt (CMD)**
```cmd
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```
The result is `installer\LectureCapture-Setup.exe`.

## License
This project is licensed under the [MIT License](LICENSE)
