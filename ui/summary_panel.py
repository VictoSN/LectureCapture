from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit
from PyQt6.QtCore import pyqtSignal, QTimer

from ui.styles import create_label, create_button

class SummaryPanel(QWidget):
    summarize_clicked = pyqtSignal()
    summary_text_changed = pyqtSignal(str) # new text
    immediate_change = pyqtSignal()
    
    def __init__(self, icons_dir) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()

        # Header Layout        
        summary_w, self.summarize_engine_label = create_label(icons_dir / 'summarize.svg', 'AI summary')
        header.addWidget(summary_w)
        
        self.summary_button = create_button(icons_dir / 'sparkle.svg', self.summarize_clicked, text="Summarize", width=130, icon_size=14)
        header.addWidget(self.summary_button)

        # Summary        
        self.summary = QTextEdit()

        timer = QTimer(self.summary)
        timer.setSingleShot(True)
        self.summary._save_timer = timer

        self.summary.textChanged.connect(self.immediate_change)
        self.summary.textChanged.connect(lambda: self.summary._save_timer.start(500))
        
        self.summary._save_timer.timeout.connect(
            lambda w=self.summary:
                self.summary_text_changed.emit(w.toPlainText())
        )

        main_layout.addLayout(header)
        main_layout.addWidget(self.summary, stretch=1)
        self.setLayout(main_layout)