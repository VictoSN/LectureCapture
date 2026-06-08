import mss
import sounddevice as sd
import win32gui
import pathlib as Path

from PyQt6.QtWidgets import QComboBox, QSpinBox
from ui.styles import load_icon

def _app_name(title: str) -> str:
    # Most apps put their display name last, after a dash. Keep just that, e.g.
    # "main.py - LectureCapture - Visual Studio Code" -> "Visual Studio Code".
    for sep in (" - ", " — ", " – ", " | "):
        if sep in title:
            return title.rsplit(sep, 1)[-1].strip()
    return title.strip()


def _window_detail(title: str) -> str:
    # The part before the app name, used only to tell apart several windows of
    # the same app.
    for sep in (" - ", " — ", " – ", " | "):
        if sep in title:
            return title.rsplit(sep, 1)[0].strip()
    return title.strip()


def setup_source(source_dropdown: QComboBox, icons_dir: Path) -> None:
    from collections import Counter
    source_dropdown.clear()

    # Get monitors first
    with mss.mss() as sct:
        # Pair each monitor with its true mss index (1-based, skipping monitors[0] which is the virtual combined screen)
        monitors_with_index = [(i, sct.monitors[i]) for i in range(1, len(sct.monitors))]
        monitors_with_index.sort(key=lambda x: not x[1].get('is_primary', False)) # primary first

        monitor_icon = load_icon(icons_dir / "monitor.svg")
        for display_num, (mss_index, m) in enumerate(monitors_with_index, 1):
            source_dropdown.addItem(
                monitor_icon,
                f"Screen {display_num} | {m['width']}x{m['height']}",
                {"type": "monitor", "index": mss_index}
            )

    # Collect windows, then label them by application name. The full title is only
    # used when several windows share an app, so the list stays easy to scan.
    _EXCLUDED = {"LectureCapture", "Program Manager", ""}
    windows = []
    def collect(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and _app_name(title) not in _EXCLUDED:
                windows.append((hwnd, title))
    win32gui.EnumWindows(collect, None)

    window_icon = load_icon(icons_dir / "window.svg")
    counts = Counter(_app_name(title) for _, title in windows)
    for hwnd, title in windows:
        name = _app_name(title)
        label = name if counts[name] == 1 else f"{name} — {_window_detail(title)}"
        source_dropdown.addItem(
            window_icon,
            label,
            {"type": "window", "hwnd": hwnd, "app_name": name}
        )
    
def setup_audio(audio_dropdown: QComboBox, icons_dir: Path) -> None:
    audio_dropdown.clear()
    devices = sd.query_devices()
    
    speaker_icon = load_icon(icons_dir / "speaker.svg")
    mic_icon = load_icon(icons_dir / "microphone.svg")

    audio_dropdown.addItem(speaker_icon, "System Audio (Loopback)", {"type": "loopback", "device_id": None})

    for i, device in enumerate(devices):
        if device["max_input_channels"] > 0 and device["hostapi"] == 0:
            audio_dropdown.addItem(mic_icon, f"{device['name']}", {"type": "microphone", "device_id": i})
            
def update_coord_ranges(monitor_index: int, x: QSpinBox, y: QSpinBox, width: QSpinBox, height: QSpinBox) -> None:
    with mss.mss() as sct:
        m = sct.monitors[monitor_index]
        x.setRange(0, m["width"])
        y.setRange(0, m["height"])
        width.setRange(0, m["width"])
        height.setRange(0, m["height"])