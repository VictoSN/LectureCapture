import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QTimer
from ui.main_window import MainWindow, ICONS_DIR
from core.resources import configure_bundled_tesseract
import ctypes

if __name__ == "__main__":
    configure_bundled_tesseract()  # point pytesseract at the bundled binary when frozen
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LectureCapture")
    app = QApplication(sys.argv)
    # Use the multi-resolution .ico (not the single-size PNG) and set it app-wide so
    # Windows always has a taskbar-sized icon — a lone PNG on the window intermittently
    # drops out when Windows asks for a size the PNG can't supply.
    icon = QIcon(str(ICONS_DIR / 'logo.ico'))
    app.setWindowIcon(icon)
    window = MainWindow()
    window.show()
    # On a COLD BOOT the taskbar button is often created before Qt has propagated the
    # window icon to the native HWND, so the icon is missing on the very first launch
    # after a restart (Windows caches that, and every later launch shows it correctly).
    # Re-assert the icon a moment after the window is shown — once the taskbar button
    # exists — so the first post-reboot launch is correct too. Tune the delay up if it
    # still misses on slower machines.
    QTimer.singleShot(250, lambda: (app.setWindowIcon(icon), window.setWindowIcon(icon)))
    sys.exit(app.exec())