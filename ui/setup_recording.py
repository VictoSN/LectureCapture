import mss
import sounddevice as sd

from PyQt6.QtWidgets import QComboBox, QSpinBox

def setup_monitor(monitor_dropdown: QComboBox) -> None:
    monitor_dropdown.clear()

    with mss.mss() as sct:
        monitors_with_index = list(enumerate(sct.monitors[1:], 1)) # [(1, {...}), (2, {...})]
        monitors_with_index.sort(key=lambda x: not x[1].get('is_primary', False)) # primary first

        for display_num, (mss_index, m) in enumerate(monitors_with_index, 1):
            monitor_dropdown.addItem(
                f"Monitor {display_num} | {m['width']}x{m['height']} ({m['left']},{m['top']})", mss_index
            )

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