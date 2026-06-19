"""A scrollable, chaptered help/guide panel (a splitter sibling shown via
show_panel("help"), replacing the old keyboard-shortcuts popup).

Each chapter shows a theme-matched screenshot from assets/screenshots/light_mode|dark_mode;
a chapter whose screenshot doesn't exist yet falls back to a captioned placeholder box.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QGridLayout, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QShortcut, QKeySequence, QPixmap

from ui.styles import check_theme
from ui.scalable_image_label import ScalableImageLabel
from core.resources import resource_root

SCREENSHOTS_DIR = resource_root() / "assets" / "screenshots"


# (chapter title, intro paragraph, [body paragraphs], image caption, screenshot filename)
# Screenshots live in assets/screenshots/light_mode|dark_mode/<filename> and are matched
# to the active theme; a missing file falls back to a captioned placeholder box.
CHAPTERS = [
    (
        "Getting Started",
        "LectureCapture records what's on your screen and what's said during a lecture, "
        "then turns it into searchable notes, summaries, and quizzes.",
        [
            "Create a session with the + button in the title bar (or Ctrl+T), give it a "
            "name and a category, then open it from the sidebar.",
            "Each session keeps its slides (captured as images + OCR text), the spoken "
            "transcript, an optional AI summary, and a quiz — all in one place.",
        ],
        "Overview of the main window",
        "getting_started.png",
    ),
    (
        "Recording a Session",
        "Press Record (or Ctrl+F) to open the recording panel and choose what to capture.",
        [
            "Pick a capture source — a screen region (Mouse Select), a specific window, or a "
            "whole monitor — and an audio input. Set the capture interval (how often a slide "
            "snapshot is taken).",
            "While recording, use Capture Now (Ctrl+Return) to grab a slide immediately, and "
            "Return to stop (with a confirmation).",
        ],
        "The recording setup panel",
        "recording.png",
    ),
    (
        "The Workspace: OCR · Audio · Summary",
        "An open session shows three panels side by side. Toggle any of them with the header "
        "buttons or Shift+1 / Shift+2 / Shift+3.",
        [
            "OCR shows each captured slide and the text read from it. Audio shows the spoken "
            "transcript, lined up with the slide that was on screen. Summary holds the AI "
            "summary.",
            "Turn on Scroll Sync to scroll the slides and transcript together. You can edit "
            "any text directly — changes save automatically.",
        ],
        "The three-panel workspace",
        "workspace.png",
    ),
    (
        "Translate & Define",
        "Select any text in a panel and right-click to look it up with Gemini.",
        [
            "Choose Define to get a short explanation, or Translate to and pick a language "
            "(or type your own). The result appears in a small pop-up card you can copy from.",
            "This needs a Gemini API key (see Settings) but works whether you're in Local or "
            "API mode.",
        ],
        "Right-click translate / define menu",
        "translate_define.png",
    ),
    (
        "AI Summary",
        "Press Summarize to condense the whole session into a structured set of notes.",
        [
            "With a Gemini key it produces a markdown summary with headings and key terms; "
            "without one it falls back to a quick on-device summary.",
            "The summary is saved with the session and can be edited like any other text.",
        ],
        "A generated summary",
        "summary.png",
    ),
    (
        "Quiz",
        "Press Quiz to generate a self-test from the session's content with Gemini.",
        [
            "The number of questions scales to how much material there is — a mix of "
            "multiple-choice and true/false, graded automatically. Use Enter for the next "
            "question and Esc for the previous one.",
            "Your quiz is saved, so you can review the answers, retake it, or regenerate it "
            "after the session content changes. (Needs a Gemini API key.)",
        ],
        "Answering a quiz question",
        "quiz.png",
    ),
    (
        "Settings",
        "Open Settings (gear icon or Ctrl+S) to control how recordings are processed and to "
        "tune the app.",
        [
            "Processing: choose Local (everything runs on this device, private, no internet) "
            "or API (send chosen steps to Google Gemini for higher accuracy). Translate / "
            "Define and Quiz always use the Gemini key.",
            "Gemini API key: paste your key and use Test API Connection to see which models "
            "are available and their daily limits. Local Speech Model: pick the Whisper model "
            "for on-device transcription, or run Detect Hardware to get a recommendation.",
            "Also here: light / dark theme, new-session defaults, start/stop sound effects, "
            "and exporting or importing sessions.",
        ],
        "The settings page",
        "settings.png",
    ),
]


SHORTCUT_SECTIONS = [
    ("General", [
        ("Ctrl+T",  "New session"),
        ("Ctrl+S",  "Settings"),
        ("Ctrl+D",  "Session properties"),
        ("Ctrl+F",  "Recording panel"),
        ("Shift+4", "Toggle sidebar"),
        ("Esc",     "Close the current panel"),
    ]),
    ("Panels", [
        ("Shift+1", "Toggle OCR panel"),
        ("Shift+2", "Toggle Audio panel"),
        ("Shift+3", "Toggle Summary panel"),
    ]),
    ("During Recording", [
        ("Return",      "Stop recording (with confirmation)"),
        ("Ctrl+Return", "Capture now"),
    ]),
    ("In a Quiz", [
        ("Enter", "Next question"),
        ("Esc",   "Previous question"),
    ]),
]


class HelpPanel(QWidget):
    close_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("helpPanel")

        # (image-holder layout, caption, filename) per chapter, so images can be swapped
        # when the theme changes. Resolve the active theme the way load_icon does.
        self._image_slots: list[tuple[QVBoxLayout, str, str]] = []
        self._dark = check_theme(str(QSettings("LectureCapture", "LectureCapture").value("theme", "auto")))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(14)
        scroll.setWidget(content)

        header = QHBoxLayout()
        title = QLabel("Help & Guide")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setToolTip("Close help (Esc)")
        self.close_button.clicked.connect(self.close_requested)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        intro = QLabel("A quick guide to recording lectures and getting notes, summaries, "
                       "and quizzes out of them.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        for title_text, intro_text, paragraphs, image_caption, image_file in CHAPTERS:
            layout.addWidget(self._chapter(title_text, intro_text, paragraphs, image_caption, image_file))

        layout.addWidget(self._shortcuts_chapter())
        layout.addStretch()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close_requested.emit)

    def _chapter(self, title: str, intro: str, paragraphs: list[str],
                 image_caption: str, image_file: str) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 8, 0, 0)
        col.setSpacing(8)

        head = QLabel(title)
        head.setObjectName("sectionHeader")
        col.addWidget(head)

        lead = QLabel(intro)
        lead.setWordWrap(True)
        col.addWidget(lead)

        # An image holder whose contents (real screenshot or placeholder) are filled by
        # _load_image, and refilled when the theme changes.
        holder = QVBoxLayout()
        holder.setContentsMargins(0, 0, 0, 0)
        col.addLayout(holder)
        self._image_slots.append((holder, image_caption, image_file))
        self._load_image(holder, image_caption, image_file)

        for para in paragraphs:
            p = QLabel("• " + para)
            p.setWordWrap(True)
            col.addWidget(p)
        return box

    def _load_image(self, holder: QVBoxLayout, caption: str, filename: str) -> None:
        # Clear whatever's there, then add the theme-matched screenshot, or a captioned
        # placeholder box if that file doesn't exist yet.
        while holder.count():
            w = holder.takeAt(0).widget()
            if w:
                w.deleteLater()
        path = SCREENSHOTS_DIR / ("dark_mode" if self._dark else "light_mode") / filename
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                holder.addWidget(self._framed_image(pixmap))
                return
        ph = QLabel(f"🖼  {caption}")
        ph.setObjectName("helpImage")
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph.setMinimumHeight(130)
        holder.addWidget(ph)

    def _framed_image(self, pixmap: QPixmap) -> QWidget:
        # A thin coral frame around the screenshot so its edges don't bleed into the panel.
        frame = QFrame()
        frame.setObjectName("helpScreenshot")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(3, 3, 3, 3)  # 3px coral mat
        inner.addWidget(ScalableImageLabel(pixmap))
        return frame

    def refresh_theme(self, theme: str = None) -> None:
        """Swap every chapter screenshot to the folder matching the active theme."""
        self._dark = check_theme(theme) if theme else self._dark
        for holder, caption, filename in self._image_slots:
            self._load_image(holder, caption, filename)

    def _shortcuts_chapter(self) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 8, 0, 0)
        col.setSpacing(8)

        head = QLabel("Keyboard Shortcuts")
        head.setObjectName("sectionHeader")
        col.addWidget(head)

        for idx, (title, rows) in enumerate(SHORTCUT_SECTIONS):
            sub = QLabel(title)
            sub.setObjectName("muted")
            sub.setContentsMargins(0, 8 if idx else 0, 0, 2)
            col.addWidget(sub)
            col.addLayout(self._shortcut_grid(rows))
        return box

    def _shortcut_grid(self, rows: list[tuple[str, str]]) -> QGridLayout:
        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, 150)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        for i, (combo, desc) in enumerate(rows):
            grid.addWidget(self._keycaps(combo), i, 0)
            grid.addWidget(QLabel(desc), i, 1)
        return grid

    @staticmethod
    def _keycaps(combo: str) -> QWidget:
        """Render 'Ctrl+T' as separate key-cap chips joined by '+'."""
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        for i, key in enumerate(k.strip() for k in combo.split("+")):
            if i:
                plus = QLabel("+")
                plus.setObjectName("muted")
                row.addWidget(plus)
            cap = QLabel(key)
            cap.setObjectName("kbd")
            row.addWidget(cap)
        row.addStretch()
        return w
