import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.resources import configure_bundled_tesseract
import ctypes

if __name__ == "__main__":
    configure_bundled_tesseract()  # point pytesseract at the bundled binary when frozen
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LectureCapture")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())