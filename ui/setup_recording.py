import mss
import sounddevice as sd
import win32gui

from PyQt6.QtWidgets import QComboBox, QSpinBox

def setup_source(source_dropdown: QComboBox) -> None:
    source_dropdown.clear()

    # Get monitors first
    with mss.mss() as sct:
        # Pair each monitor with its true mss index (1-based, skipping monitors[0] which is the virtual combined screen)
        monitors_with_index = [(i, sct.monitors[i]) for i in range(1, len(sct.monitors))]
        monitors_with_index.sort(key=lambda x: not x[1].get('is_primary', False)) # primary first

        for display_num, (mss_index, m) in enumerate(monitors_with_index, 1):
            source_dropdown.addItem(
                f"Monitor {display_num} | {m['width']}x{m['height']}", {"type": "monitor", "index": mss_index}
            )

    # Get windows
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            source_dropdown.addItem(
                F"[Window] {win32gui.GetWindowText(hwnd)}", {"type": "window", "hwnd": hwnd}
            )
    
    win32gui.EnumWindows(callback, None)
    
def setup_audio(audio_dropdown: QComboBox) -> None:
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device["max_input_channels"] > 0 and device["hostapi"] == 0:
            audio_dropdown.addItem(device["name"], i)

def update_coord_ranges(monitor_index: int, x: QSpinBox, y: QSpinBox, width: QSpinBox, height: QSpinBox) -> None:
    with mss.mss() as sct:
        m = sct.monitors[monitor_index]
        x.setRange(0, m["width"])
        y.setRange(0, m["height"])
        width.setRange(0, m["width"])
        height.setRange(0, m["height"])