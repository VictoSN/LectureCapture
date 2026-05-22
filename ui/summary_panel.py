from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
)

class SummaryPanel(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout()
        header = QHBoxLayout()

        # Header Layout
        summary_label = QLabel("AI summary")
        header.addWidget(summary_label)
        self.summary_button = QPushButton("Summarize")
        header.addWidget(self.summary_button)

        # Summary        
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)

        main_layout.addLayout(header)
        main_layout.addWidget(self.summary, stretch=1)
        self.setLayout(main_layout)