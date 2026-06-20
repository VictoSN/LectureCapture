import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
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
    app.setWindowIcon(QIcon(str(ICONS_DIR / 'logo.ico')))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())