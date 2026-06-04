from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
)
from PyQt6.QtCore import pyqtSignal, QTimer

class SummaryPanel(QWidget):
    summarize_clicked = pyqtSignal()
    summary_text_changed = pyqtSignal(str) # new text
    immediate_change = pyqtSignal()
    
    def __init__(self) -> None:
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()

        # Header Layout
        summary_label = QLabel("AI summary")
        header.addWidget(summary_label)
        self.summary_button = QPushButton("Summarize")
        self.summary_button.clicked.connect(self.summarize_clicked)
        self.summary_button.setDisabled(False)
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