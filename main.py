import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QTimer
from ui.main_window import MainWindow, ICONS_DIR
from ui.styles import install_justify_filter
from core.resources import configure_bundled_tesseract, APP_VERSION
from core.applog import get_logger, install_excepthook
import ctypes

if __name__ == "__main__":
    log = get_logger()
    install_excepthook()
    log.info("LectureCapture %s starting (frozen=%s)", APP_VERSION, getattr(sys, "frozen", False))
    configure_bundled_tesseract()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LectureCapture")
    app = QApplication(sys.argv)
    install_justify_filter()
    icon = QIcon(str(ICONS_DIR / 'logo.ico'))
    app.setWindowIcon(icon)
    window = MainWindow()
    window.show()
    # Re-assert icon after window is shown (Windows cold-boot taskbar workaround).
    QTimer.singleShot(250, lambda: (app.setWindowIcon(icon), window.setWindowIcon(icon)))
    sys.exit(app.exec())