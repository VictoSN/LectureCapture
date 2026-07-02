"""A two-level help/guide panel (a splitter sibling shown via show_panel("help")).

The main page lists every chapter as a clickable row; picking one swaps to that
chapter's page, where an annotated screenshot's numbered callouts are explained by
matching numbered notes underneath. Screenshots are matched to the active theme
from assets/screenshots/light_mode|dark_mode; a chapter whose screenshot doesn't
exist yet falls back to a captioned placeholder box.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QGridLayout, QFrame, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QShortcut, QKeySequence, QPixmap, QIcon

from ui.styles import check_theme
from ui.scalable_image_label import ScalableImageLabel
from core.resources import resource_root, APP_VERSION

SCREENSHOTS_DIR = resource_root() / "assets" / "screenshots"
NUMBERING_DIR = resource_root() / "assets" / "icons" / "numbering"


def _number_chip(number: str) -> QLabel:
    """The coral callout circle: the SVG from assets/icons/numbering, or a
    stylesheet-drawn stand-in if that file doesn't exist. QIcon.pixmap already
    renders at the display's device-pixel ratio (Qt 6), so 24 logical px is
    requested as-is — pre-multiplying by the DPR makes the pixmap overflow the
    label and get clipped."""
    chip = QLabel()
    chip.setFixedSize(24, 24)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    path = NUMBERING_DIR / f"{number}.svg"
    if path.exists():
        chip.setPixmap(QIcon(str(path)).pixmap(24, 24))
    else:
        chip.setObjectName("helpNum")
        chip.setText(number)
    return chip


# Each chapter is (title, card blurb, blocks). The title + blurb make the clickable
# card on the main page; the blocks build the chapter's own page top-to-bottom:
#   ("p", text)                      — a paragraph (rich text if it embeds an <a> tag)
#   ("img", base, caption)           — full-width screenshot "<base> Light|Dark
#                                      Mode.drawio.png", matched to the active theme
#   ("items", [(num, name, text)])   — numbered notes matching the screenshot callouts
#   ("figure", base, caption, items) — notes on the left, screenshot on the right, so
#                                      the callouts and their explanations share the
#                                      view; an item is (num, name, text) for a numbered
#                                      note, or a plain string for a paragraph
# blocks=None marks a chapter that hasn't been written yet (placeholder page).
CHAPTERS = [
    (
        "Getting Started",
        "A tour of the main window and what every button does.",
        [
            ("p",
             "LectureCapture records what's on your screen and what's said during a "
             "lecture, then turns it into searchable notes, summaries, and quizzes. "
             "Everything starts from this window — each number in the screenshot is "
             "explained beside it."),
            ("figure", "Help Panel 1", "The main window with every control numbered", [
                ("1", "Panel toggles",
                 "Show or hide the sidebar and the three workspace panels — Screen "
                 "OCR, Audio transcript, and AI summary (Shift+1 to Shift+4)."),
                ("2", "Session list",
                 "Every saved session, grouped by date. Click one to open it in the "
                 "workspace."),
                ("3", "Screen OCR panel",
                 "Each slide captured during a recording, along with the text read "
                 "from it."),
                ("4", "Audio transcript panel",
                 "Everything that was said, transcribed and lined up with the slide "
                 "that was on screen at the time."),
                ("5", "AI summary panel",
                 "The generated notes for the session — see the Summarization "
                 "chapter."),
                ("6", "Properties button",
                 "Opens the session's details — name, category, and more (Ctrl+D)."),
                ("7", "Scroll Sync button",
                 "Locks the slides and transcript together so they scroll as one."),
                ("8", "Quiz button",
                 "Opens the quiz panel to test yourself on the session's content."),
                ("9", "Import button",
                 "Brings an existing audio or video file into the app — see the "
                 "Importing Media chapter."),
                ("10", "Record button",
                 "Starts recording a lecture (Ctrl+F) — see the Recording chapter."),
                ("11", "New session · Settings · Help",
                 "Create a new session (Ctrl+T), open Settings (Ctrl+S), or open "
                 "this guide (Ctrl+G)."),
                ("12", "Information bar",
                 "Shows the recording time, save status, and which OCR and speech "
                 "engines are in use."),
            ]),
        ],
    ),
    (
        "Settings",
        "Pick a processing mode and set up the speech model or API key before your "
        "first recording.",
        [
            ("p",
             "Before you can record, the app needs a way to turn audio into text: "
             "open Settings (gear icon or Ctrl+S) and either download a local "
             "speech model or add a Gemini API key first. The six controls below "
             "are the ones worth understanding up front."),
            ("figure", "Help Panel 11", "The Settings page", [
                ("1", "Processing mode",
                 "Where your recordings are processed. Local runs everything on "
                 "this device — private, and works without internet. API sends the "
                 "steps you choose to Google Gemini for higher accuracy, which "
                 "needs a key (5) and an internet connection."),
                ("2", "Local Speech Model",
                 "The on-device Whisper model that turns recorded audio into text. "
                 "Bigger models are more accurate but slower; smaller ones stay "
                 "real-time on modest hardware. Picking one downloads it once "
                 "(needs internet) and shows a ✓ when it's installed."),
                ("3", "Detect Hardware",
                 "Scans this PC — graphics card, memory — and recommends the speech "
                 "model that best fits it, so you don't have to guess."),
                ("4", "Google Gemini API Key",
                 "Needed for Summary, Quiz, and Translate / Define, and for any "
                 "steps you run through Gemini in API mode. The free tier is "
                 "enough — the Getting a Gemini API Key chapter walks through "
                 "creating one."),
                ("5", "Use API for",
                 "In API mode, choose which steps go through Gemini: OCR (reading "
                 "slides) and/or Audio (speech transcription). Anything unticked "
                 "keeps running locally."),
                ("6", "Test API Connection",
                 "Checks that your key works and lists which Gemini models are "
                 "available to it, along with their daily free-tier limits."),
            ]),
            ("p",
             "Everything else on the page — appearance, recording preferences, "
             "sound effects, session export / import — is explained right beside "
             "the control in Settings itself."),
        ],
    ),
    (
        "Creating a New Session",
        "Set up a session to hold a lecture's slides, transcript, and notes.",
        [
            ("p",
             "Press the + button in the title bar (or Ctrl+T) to create a session — "
             "the container that holds one lecture's slides, transcript, summary, "
             "and quiz."),
            ("figure", "Help Panel 2", "The New Session form", [
                ("1", "Session Name",
                 "What the session is called in the sidebar — the lecture's topic "
                 "or week usually works well."),
                ("2", "Activity Category",
                 "The kind of class this is — Lab, Tutorial, Lecture, Workshop, or "
                 "one of your own (pick “Add new…” to type it). It colours the "
                 "session's stripe in the sidebar, and the sidebar can filter by "
                 "it."),
                ("3", "Module Category",
                 "The course or module the session belongs to — also filterable "
                 "in the sidebar. Optional: “None” leaves it unassigned."),
            ]),
            ("p",
             "“Create” saves the session and it appears in the sidebar, ready to "
             "record into. “Cancel” backs out without saving."),
        ],
    ),
    (
        "Recording a Session",
        "Choose what to capture and control the recording.",
        [
            ("p",
             "With a session open, press “Record” (or Ctrl+F) to set up what gets "
             "captured. “Start Recording” begins the capture; “Cancel” backs out "
             "without starting."),
            ("figure", "Help Panel 3", "The recording setup form", [
                ("1", "Interval (s)",
                 "How often a slide snapshot is taken, in seconds. Shorter "
                 "intervals catch fast slide changes but store more captures."),
                ("2", "Capture Method",
                 "How the capture area is chosen: Mouse Select (drag a rectangle "
                 "over the area you want), Coordinates (type the exact region), or "
                 "Full Window (capture a whole window or screen)."),
                ("3", "Source",
                 "What to record — a specific window or a whole monitor, picked "
                 "from everything currently open."),
                ("4", "Audio",
                 "Where the sound comes from — a microphone, or System Audio "
                 "(Loopback) to record what's playing on the PC, ideal for online "
                 "lectures."),
            ]),
            ("p",
             "While recording: Ctrl+Enter grabs a slide immediately (on top of the "
             "interval snapshots), and Enter stops the recording after a "
             "confirmation."),
        ],
    ),
    (
        "After Recording",
        "What a finished session looks like in the workspace.",
        [
            ("figure", "Help Panel 4", "A freshly recorded session", [
                "When a recording stops, the session is already filled in — "
                "nothing else to do. Every snapshot became a panel in Screen OCR: "
                "the slide image with the text read from it underneath, stamped "
                "with when it appeared. The trash button removes a bad capture; "
                "the collapse button shrinks one you don't need open.",
                "The Audio transcript holds everything that was said, timestamped "
                "and lined up with the slide that was on screen at the time. Turn "
                "on “Scroll Sync” to scroll slides and speech together.",
                "Both panels start at “Locked” so nothing gets nudged by "
                "accident — click “Locked” to switch the panel to “Editable” and "
                "fix any misread or misheard text. Changes save automatically. "
                "The AI summary stays empty until you press “Summarize” (see the "
                "Summarization chapter).",
            ]),
        ],
    ),
    (
        "Session Properties",
        "View and edit a session's details.",
        [
            ("p",
             "Press “Properties” (or Ctrl+D) to open the session's details next "
             "to the workspace."),
            ("figure", "Help Panel 5", "The Properties panel", [
                ("1", "Session Name",
                 "Rename the session — the sidebar updates on save."),
                ("2", "Activity Category",
                 "Change the kind of class this was (Lab, Lecture, your own…) — "
                 "it recolours the session's sidebar stripe."),
                ("3", "Module Category",
                 "Change which course or module the session belongs to."),
                ("4", "Dates",
                 "A read-only record of the session: when it was recorded, last "
                 "modified, and when its summary and quiz were generated."),
                ("5", "Delete · Duplicate",
                 "“Delete” removes the session and everything in it (asks "
                 "first). “Duplicate” makes a full copy — captures, summary, "
                 "quiz and all."),
            ]),
            ("p",
             "“Save” applies your changes; “Close” dismisses the panel without "
             "saving them."),
        ],
    ),
    (
        "Summarization",
        "Condense a session into structured AI notes.",
        [
            ("p",
             "The AI summary panel turns the whole session — slides and speech — "
             "into a compact set of revision notes."),
            ("figure", "Help Panel 6", "A generated summary", [
                ("1", "Summarize",
                 "Generates the notes. With a Gemini key you get structured "
                 "markdown with headings and key terms; without one, a quick "
                 "on-device summary is used instead. Run it again after editing "
                 "the session to refresh the notes."),
                ("2", "Preview / Edit",
                 "Switches the summary between the rendered view and plain text "
                 "you can edit yourself — your edits are saved with the session."),
            ]),
        ],
    ),
    (
        "Translate & Define",
        "Look up or translate any text you select.",
        [
            ("p",
             "Select any text in a panel — a term on a slide, a phrase in the "
             "transcript or summary — and right-click to look it up with Gemini. "
             "This needs a Gemini API key, but works whether you're in Local or "
             "API mode."),
            ("figure", "Help Panel 7", "The right-click lookup menu", [
                ("1", "Define",
                 "Asks for a short explanation of the selected word or phrase, in "
                 "the context it appeared in."),
                ("2", "Translate to",
                 "Opens a list of languages — pick one, or type your own at the "
                 "bottom of the list."),
            ]),
            ("figure", "Help Panel 7.1", "A definition result", [
                ("1", "Definition card",
                 "The explanation appears in a small pop-up card over the "
                 "workspace — “Copy” puts it on the clipboard, and it closes "
                 "with the ✕ or a click elsewhere."),
            ]),
            ("figure", "Help Panel 7.2", "A translation result", [
                ("1", "Translation card",
                 "Translations appear the same way, with the target language in "
                 "the title."),
            ]),
        ],
    ),
    (
        "Importing Media",
        "Bring an existing audio or video file into the app.",
        [
            ("p",
             "Already have the lecture as a file — a recorded video or audio? "
             "Open the session it belongs in, press “Import”, and pick the file. "
             "It's processed just like a live recording: speech is transcribed, "
             "and video frames become slide captures with their text read."),
            ("figure", "Help Panel 8", "The Import media dialog", [
                ("1", "Playback",
                 "Play the file and drag the slider to find where the actual "
                 "lecture starts."),
                ("2", "Start point",
                 "Transcription begins from the position you've seeked to — handy "
                 "for skipping intros or dead air at the start."),
                ("3", "Transcribe from here",
                 "Press “Transcribe from here” to start processing the file from "
                 "that point."),
            ]),
            ("figure", "Help Panel 8.1", "An import in progress", [
                ("1", "Progress",
                 "The footer shows how far through the file the transcription "
                 "has got — the session fills in as it goes."),
                ("2", "Pause · Stop",
                 "“Pause” suspends the import; “Stop” ends it early, keeping "
                 "everything processed so far."),
            ]),
        ],
    ),
    (
        "Quiz",
        "Generate a self-test from a session's content.",
        [
            ("p",
             "Press “Quiz” to test yourself on a session. It needs the session's "
             "summary to exist first (press “Summarize” if you haven't) and a "
             "Gemini API key."),
            ("figure", "Help Panel 9", "The quiz start page", [
                ("1", "Generate Quiz",
                 "Builds a fresh quiz from the session's content with Gemini. The "
                 "number of questions scales with how much material there is."),
            ]),
            ("figure", "Help Panel 9.1", "Generating the quiz", [
                "Generation takes a few seconds — the page shows which Gemini "
                "model is writing your questions.",
            ]),
            ("figure", "Help Panel 9.2", "Answering a question", [
                "Questions are a mix of multiple choice and true / false. Pick an "
                "answer and move on — Enter (or “Next”) advances, Esc (or "
                "“Previous”) goes back if you want to change something.",
            ]),
            ("figure", "Help Panel 9.3", "The results review", [
                "At the end you get a score and a card per question: your answer, "
                "the correct one, and a short explanation. “Retake” runs the same "
                "quiz again, and the quiz is saved with the session so you can "
                "review it any time — or regenerate it after the content changes.",
            ]),
        ],
    ),
    (
        "Getting a Gemini API Key",
        "Get a free key from Google AI Studio for the AI features.",
        [
            ("p",
             "The AI features — Summary, Quiz, and Translate / Define — use "
             "Google's Gemini API, which has a free tier. Go to "
             '<a href="https://aistudio.google.com/api-keys" style="color:#c15f3c;">AI Studio</a> '
             "and sign in with a Google account (creating one is free), then "
             "follow the steps below."),
            ("figure", "Help Panel 10", "The AI Studio API Keys page", [
                ("1", "Create API key",
                 "On the API Keys page, press “Create API key” (top right) to "
                 "start."),
            ]),
            ("figure", "Help Panel 10.1", "Naming the key and picking a project", [
                ("1", "Choose a project",
                 "A key must belong to a Google Cloud project. If the dropdown "
                 "says “No Cloud Projects Available”, open it…"),
                ("2", "Create project",
                 "…and pick “Create project” — AI Studio makes one for you on "
                 "the spot. Name the key anything you like."),
            ]),
            ("figure", "Help Panel 10.2", "Creating the key", [
                ("1", "Create key",
                 "With a name and project set, press “Create key”. A long key "
                 "starting with “AIza…” is generated."),
            ]),
            ("figure", "Help Panel 10.3", "Copying the finished key", [
                ("1", "Copy key",
                 "Copy it, then in LectureCapture open Settings (Ctrl+S), paste "
                 "it into the “Google Gemini API Key” box, press Save, and run "
                 "“Test API Connection” to confirm it works."),
            ]),
            ("p",
             "Troubleshooting — “invalid API key”: the key was mistyped or "
             "revoked, so regenerate it. “Daily limit reached”: you’ve hit the "
             "free-tier cap, which resets the next day. “Temporarily busy”: a "
             "transient server issue, just retry."),
        ],
    ),
]

API_KEY_CHAPTER_TITLE = "Getting a Gemini API Key"


SHORTCUT_SECTIONS = [
    ("General", [
        ("Ctrl+T",  "New session"),
        ("Ctrl+S",  "Settings"),
        ("Ctrl+G",  "Help & guide"),
        ("Ctrl+D",  "Session properties"),
        ("Ctrl+F",  "Recording panel"),
        ("Esc",     "Close the current panel"),
    ]),
    ("Panels", [
        ("Shift+1", "Toggle sidebar"),
        ("Shift+2", "Toggle OCR panel"),
        ("Shift+3", "Toggle Audio panel"),
        ("Shift+4", "Toggle Summary panel"),
    ]),
    ("During Recording", [
        ("Enter",      "Stop recording (with confirmation)"),
        ("Ctrl+Enter", "Capture now"),
    ]),
    ("In a Quiz", [
        ("Enter", "Next question"),
        ("Esc",   "Previous question"),
    ]),
]


class ChapterTile(QFrame):
    """A clickable card on the main help page: number chip + title, blurb below."""

    clicked = pyqtSignal()

    def __init__(self, number: str, title: str, blurb: str) -> None:
        super().__init__()
        self.setObjectName("helpRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(_number_chip(number))
        head = QLabel(title)
        head.setObjectName("helpRowTitle")
        head.setWordWrap(True)
        top.addWidget(head, 1)
        col.addLayout(top)

        sub = QLabel(blurb)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        col.addWidget(sub)
        col.addStretch()

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class HelpPanel(QWidget):
    close_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("helpPanel")

        # (image-holder layout, caption, screenshot base name) per image, so every
        # screenshot can be swapped when the theme changes. Resolve the active theme
        # the way load_icon does.
        self._image_slots: list[tuple[QVBoxLayout, str, str]] = []
        self._dark = check_theme(str(QSettings("LectureCapture", "LectureCapture").value("theme", "auto")))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page 0 is the chapter list; pages 1..N are the chapters, then shortcuts.
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        # Back and Close live in a persistent footer pinned below the stack (outside
        # the scroll areas), so they're always reachable on any page. Back only shows
        # while a chapter page is open.
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 8, 24, 12)
        footer.setSpacing(10)
        footer.addStretch()
        self.back_button = QPushButton("Back")
        self.back_button.setToolTip("Back to the topic list (Esc)")
        self.back_button.clicked.connect(self._go_home)
        self.back_button.setVisible(False)
        footer.addWidget(self.back_button)
        self.close_button = QPushButton("Close")
        self.close_button.setToolTip("Close help (Esc)")
        self.close_button.clicked.connect(self.close_requested)
        footer.addWidget(self.close_button)
        outer.addLayout(footer)
        self._stack.currentChanged.connect(lambda index: self.back_button.setVisible(index != 0))

        # Per-page scroll areas, so opening a chapter can reset its scroll position.
        self._page_scrolls: dict[int, QScrollArea] = {}
        self._api_key_index = 0

        self._stack.addWidget(self._main_page())
        for i, (title, _blurb, blocks) in enumerate(CHAPTERS):
            page, scroll = self._chapter_page(str(i + 1), title, blocks)
            index = self._stack.addWidget(page)
            self._page_scrolls[index] = scroll
            if title == API_KEY_CHAPTER_TITLE:
                self._api_key_index = index
        page, scroll = self._shortcuts_page()
        index = self._stack.addWidget(page)
        self._page_scrolls[index] = scroll

        # Esc backs out one level: chapter page → main page → close the panel.
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_escape)

    # ---- Pages ------------------------------------------------------------

    def _main_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = self._scroll_area()
        outer.addWidget(scroll)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 28)
        layout.setSpacing(10)
        scroll.setWidget(content)

        title = QLabel("Help & Guide")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        intro = QLabel("A quick guide to recording lectures and getting notes, "
                       "summaries, and quizzes out of them. Pick a topic to see a "
                       "step-by-step walkthrough.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)
        layout.addSpacing(6)

        # The 11 chapters + the shortcuts page as a 4-wide grid of cards, so the
        # whole guide is visible without scrolling.
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        tiles = [ChapterTile(str(i + 1), chapter_title, blurb)
                 for i, (chapter_title, blurb, _blocks) in enumerate(CHAPTERS)]
        tiles.append(ChapterTile(str(len(CHAPTERS) + 1), "Keyboard Shortcuts",
                                 "Every shortcut in one place."))
        for i, tile in enumerate(tiles):
            tile.clicked.connect(lambda index=i + 1: self._open(index))
            grid.addWidget(tile, i // 4, i % 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        layout.addStretch()

        version = QLabel(f"Version {APP_VERSION}")
        version.setObjectName("muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setContentsMargins(0, 16, 0, 0)
        layout.addWidget(version)
        return page

    def _chapter_page(self, number: str, title: str,
                      blocks: list | None) -> tuple[QWidget, QScrollArea]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(self._page_header(f"{number}.  {title}"))

        scroll = self._scroll_area()
        outer.addWidget(scroll)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 10, 24, 28)
        layout.setSpacing(12)
        scroll.setWidget(content)

        if blocks is None:
            ph = QLabel("This chapter is still being written.")
            ph.setObjectName("muted")
            layout.addWidget(ph)
        else:
            for block in blocks:
                self._add_block(layout, block)
        layout.addStretch()
        return page, scroll

    def _shortcuts_page(self) -> tuple[QWidget, QScrollArea]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(self._page_header(f"{len(CHAPTERS) + 1}.  Keyboard Shortcuts"))

        scroll = self._scroll_area()
        outer.addWidget(scroll)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 10, 24, 28)
        layout.setSpacing(8)
        scroll.setWidget(content)

        for idx, (title, rows) in enumerate(SHORTCUT_SECTIONS):
            sub = QLabel(title)
            sub.setObjectName("muted")
            sub.setContentsMargins(0, 8 if idx else 0, 0, 2)
            layout.addWidget(sub)
            layout.addLayout(self._shortcut_grid(rows))
        layout.addStretch()
        return page, scroll

    def _page_header(self, title: str) -> QHBoxLayout:
        # The page title, pinned above the chapter's scroll area.
        header = QHBoxLayout()
        header.setContentsMargins(24, 18, 24, 10)
        head = QLabel(title)
        head.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(head)
        header.addStretch()
        return header

    # ---- Chapter content blocks -------------------------------------------

    def _add_block(self, layout: QVBoxLayout, block: tuple) -> None:
        kind = block[0]
        if kind == "p":
            p = QLabel(block[1])
            p.setWordWrap(True)
            # Only paragraphs that embed an <a> tag are treated as rich text +
            # clickable, so plain steps with literal &, <, > stay safe.
            if "<a " in block[1]:
                p.setTextFormat(Qt.TextFormat.RichText)
                p.setOpenExternalLinks(True)
            layout.addWidget(p)
        elif kind == "img":
            _, base, caption = block
            holder = QVBoxLayout()
            holder.setContentsMargins(0, 4, 0, 4)
            layout.addLayout(holder)
            self._image_slots.append((holder, caption, base))
            self._load_image(holder, caption, base)
        elif kind == "items":
            for num, name, text in block[1]:
                layout.addWidget(self._numbered_item(num, name, text))
        elif kind == "figure":
            _, base, caption, items = block
            row = QHBoxLayout()
            row.setSpacing(18)
            notes = QVBoxLayout()
            notes.setSpacing(10)
            for item in items:
                if isinstance(item, str):
                    p = QLabel(item)
                    p.setWordWrap(True)
                    notes.addWidget(p)
                else:
                    notes.addWidget(self._numbered_item(*item))
            notes.addStretch()
            row.addLayout(notes, 35)
            holder = QVBoxLayout()
            holder.setContentsMargins(0, 4, 0, 4)
            self._image_slots.append((holder, caption, base))
            self._load_image(holder, caption, base)
            row.addLayout(holder, 65)
            layout.addLayout(row)

    def _numbered_item(self, num: str, name: str, text: str) -> QWidget:
        # The coral number chip (echoing the screenshot callouts) beside the note.
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(_number_chip(num), alignment=Qt.AlignmentFlag.AlignTop)
        body = QLabel(f"<b>{name}</b> — {text}")
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        row.addWidget(body, 1)
        return box

    # ---- Images -------------------------------------------------------------

    def _load_image(self, holder: QVBoxLayout, caption: str, base: str) -> None:
        # Clear whatever's there, then add the theme-matched screenshot, or a
        # captioned placeholder box if that file doesn't exist yet. The trailing
        # stretch keeps the image pinned to the top when its column is taller
        # (side-by-side figures), instead of the coral frame stretching to fill.
        while holder.count():
            w = holder.takeAt(0).widget()
            if w:
                w.deleteLater()
        theme = "Dark" if self._dark else "Light"
        folder = "dark_mode" if self._dark else "light_mode"
        path = SCREENSHOTS_DIR / folder / f"{base} {theme} Mode.drawio.png"
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
        if not pixmap.isNull():
            holder.addWidget(self._framed_image(pixmap))
        else:
            ph = QLabel(f"🖼  {caption}")
            ph.setObjectName("helpImage")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph.setMinimumHeight(130)
            holder.addWidget(ph)
        holder.addStretch()

    def _framed_image(self, pixmap: QPixmap) -> QWidget:
        # A thin coral frame around the screenshot so its edges don't bleed into the panel.
        frame = QFrame()
        frame.setObjectName("helpScreenshot")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(3, 3, 3, 3)  # 3px coral mat
        inner.addWidget(ScalableImageLabel(pixmap))
        return frame

    # ---- Navigation ---------------------------------------------------------

    def _open(self, index: int) -> None:
        scroll = self._page_scrolls.get(index)
        if scroll:
            scroll.verticalScrollBar().setValue(0)
        self._stack.setCurrentIndex(index)

    def _go_home(self) -> None:
        self._stack.setCurrentIndex(0)

    def _on_escape(self) -> None:
        if self._stack.currentIndex() != 0:
            self._go_home()
        else:
            self.close_requested.emit()

    def hideEvent(self, event) -> None:
        # Reopening the guide always starts from the topic list.
        self._stack.setCurrentIndex(0)
        super().hideEvent(event)

    def scroll_to_api_key(self) -> None:
        """Open the 'Getting a Gemini API Key' chapter. Used when the user clicks
        the step-by-step link in Settings so they land on the relevant page."""
        self._open(self._api_key_index)

    def refresh_theme(self, theme: str = None) -> None:
        """Swap every chapter screenshot to the folder matching the active theme."""
        self._dark = check_theme(theme) if theme else self._dark
        for holder, caption, base in self._image_slots:
            self._load_image(holder, caption, base)

    # ---- Shared helpers -------------------------------------------------------

    @staticmethod
    def _scroll_area() -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

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
