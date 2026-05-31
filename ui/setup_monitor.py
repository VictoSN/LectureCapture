import mss
from PyQt6.QtWidgets import QComboBox

def setup_monitor(monitor_dropdown: QComboBox) -> None:
    monitor_dropdown.clear()

    with mss.mss() as sct:
        monitors_with_index = list(enumerate(sct.monitors[1:], 1)) # [(1, {...}), (2, {...})]
        monitors_with_index.sort(key=lambda x: not x[1].get('is_primary', False)) # primary first

        for display_num, (mss_index, m) in enumerate(monitors_with_index, 1):
            monitor_dropdown.addItem(
                f"Monitor {display_num} | {m['width']}x{m['height']} ({m['left']},{m['top']})", mss_index
            )