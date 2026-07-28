import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QTimer, QSettings
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
    # Apply any saved UI scale factor before Qt creates the application.
    settings = QSettings("LectureCapture", "LectureCapture")
    try:
        scale = float(settings.value("ui_scale", 1.0))
    except Exception:
        scale = 1.0
    if scale > 0 and scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(scale)
    app = QApplication(sys.argv)
    install_justify_filter()
    icon = QIcon(str(ICONS_DIR / 'logo.ico'))
    app.setWindowIcon(icon)
    window = MainWindow()
    window.show()
    # Re-assert icon after window is shown (Windows cold-boot taskbar workaround).
    QTimer.singleShot(250, lambda: (app.setWindowIcon(icon), window.setWindowIcon(icon)))
    sys.exit(app.exec())