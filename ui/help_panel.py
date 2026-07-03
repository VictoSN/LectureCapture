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
             "LectureCapture records what's on your screen and what's being said "
             "during an online/hybrid lecture, then turns all of it into notes you can search, "
             "a summary, and a quiz. Everything happens in this one window, so "
             "here's a quick tour of it. Each number in the screenshot is "
             "explained next to it."),
            ("figure", "Help Panel 1", "The main window with every control numbered", [
                ("1", "Panel toggles",
                 "These four buttons show and hide the big parts of the window: "
                 "the sidebar, the Screen OCR panel, the Audio transcript panel, "
                 "and the AI summary panel. Useful when you want more room for "
                 "one of them. Shift+1 to Shift+4 do the same thing."),
                ("2", "Session list",
                 "Every session you've made, grouped by date. A session is one "
                 "lecture: its slides, transcript, summary and quiz all live in "
                 "it. Click one to open it. The search box above finds sessions "
                 "by name, and the funnel button filters the list by activity or "
                 "module."),
                ("3", "Screen OCR panel",
                 "Every slide captured during the recording, each with the text "
                 "the app read off it shown underneath."),
                ("4", "Audio transcript panel",
                 "Everything that was said in the lecture, written out with "
                 "timestamps, sitting next to the slide that was up at the time."),
                ("5", "AI summary panel",
                 "The AI-written notes for this session. It stays empty until you "
                 "press “Summarize”. There's a whole chapter on it."),
                ("6", "Properties button",
                 "Opens the session's details, like its name and categories "
                 "(Ctrl+D)."),
                ("7", "Scroll Sync button",
                 "Ties the slides and the transcript together, so scrolling one "
                 "scrolls the other and you always see matching content."),
                ("8", "Quiz button",
                 "Opens the quiz page, where you can test yourself on this "
                 "session."),
                ("9", "Import button",
                 "Brings in a lecture you already have as a video or audio file, "
                 "instead of recording it live."),
                ("10", "Record button",
                 "Starts recording a lecture into the open session (Ctrl+F)."),
                ("11", "New session, Settings and Help",
                 "The + makes a new session (Ctrl+T), the gear opens Settings "
                 "(Ctrl+S), and the question mark opens this guide (Ctrl+G)."),
                ("12", "Information bar",
                 "A small status strip: how long the recording has been running, "
                 "whether your changes are saved, and which engines are currently "
                 "reading slides and turning speech into text."),
            ]),
        ],
    ),
    (
        "Settings",
        "Set up a speech model or an API key before your first recording.",
        [
            ("p",
             "Before you can record anything, the app needs a way to turn speech "
             "into text. Open Settings with the gear icon (or Ctrl+S) and set up "
             "one of the two options: download a speech model that runs on your "
             "own PC, or paste in a Gemini API key. Without one of those, a "
             "recording would have nothing to transcribe with. The six numbered "
             "controls are the ones worth understanding, so here they are in "
             "detail."),
            ("figure", "Help Panel 11", "The Settings page", [
                ("1", "Processing mode",
                 "Decides where the heavy work happens. Local means everything "
                 "runs on your own PC: completely private, works without "
                 "internet, but the speed depends on your hardware. API sends "
                 "the work to Google Gemini instead, which is usually more "
                 "accurate at reading slides and transcribing speech, but needs "
                 "a key (4) and an internet connection."),
                ("2", "Local Speech Model",
                 "The speech recognition model used in Local mode. Bigger models "
                 "make fewer mistakes but need a stronger PC to keep up with the "
                 "lecture; smaller ones run fine on most laptops. Picking one "
                 "from the list downloads it once (you'll need internet for that "
                 "part), and a ✓ marks the models you already have."),
                ("3", "Detect Hardware",
                 "Not sure which model to pick? This checks what your PC has, "
                 "mainly the graphics card, and recommends the best model it can "
                 "comfortably run in real time."),
                ("4", "Google Gemini API Key",
                 "Paste your key here and press “Save”. Summary, Quiz and "
                 "Translate / Define always run through Gemini, so they need "
                 "this key no matter which mode you're in. The free tier is "
                 "plenty for studying, and the 'Getting a Gemini API Key' chapter "
                 "walks you through getting one."),
                ("5", "Use API for",
                 "Only matters in API mode. Tick which jobs go to Gemini: OCR "
                 "(reading the slides) and Audio (transcribing speech). Anything "
                 "you untick keeps running locally, so you can mix and match, "
                 "say Gemini for messy slides but local speech."),
                ("6", "Test API Connection",
                 "Checks that your key actually works, then lists which Gemini "
                 "models you can use and how many requests per day the free "
                 "tier allows on each."),
            ]),
            ("p",
             "The rest of the page is more self-explanatory: light and dark "
             "theme, what the recording form remembers between uses, start and "
             "stop sounds, and exporting or importing whole sessions as files. "
             "Each of those has its explanation written right next to it."),
        ],
    ),
    (
        "Creating a New Session",
        "Make a session to hold a lecture's slides, transcript, and notes.",
        [
            ("p",
             "A session is the box a lecture lives in, so you make one before "
             "you record. Press the + button in the title bar (or Ctrl+T) and "
             "you get this short form. Only three fields, and two of them are "
             "optional enough."),
            ("figure", "Help Panel 2", "The New Session form", [
                ("1", "Session Name",
                 "What the session will be called in the sidebar. The lecture's "
                 "topic or week number works well, anything you'll recognise "
                 "later."),
                ("2", "Activity Category",
                 "What kind of class this is: Lab, Tutorial, Lecture, Workshop, "
                 "or anything else you type in yourself with “Add new…”. Each "
                 "category gets its own colour on the session's card in the "
                 "sidebar, and you can filter the sidebar by it."),
                ("3", "Module Category",
                 "The course or module this session belongs to, so sessions "
                 "from the same subject stay together. It's optional, “None” is "
                 "perfectly fine, and it's also a sidebar filter."),
            ]),
            ("p",
             "“Create” saves the session and it shows up in the sidebar, ready "
             "to record into. “Cancel” throws the form away."),
        ],
    ),
    (
        "Recording a Session",
        "Choose what to capture and start recording.",
        [
            ("p",
             "Open the session you want the lecture to go into, then press "
             "“Record” (or Ctrl+F). This form decides what gets captured. Once "
             "everything looks right, “Start Recording” kicks things off and "
             "“Cancel” backs out."),
            ("figure", "Help Panel 3", "The recording setup form", [
                ("1", "Interval (s)",
                 "How often a snapshot of the screen is taken, from 1 to 30 "
                 "seconds. A short interval catches quick slide changes but "
                 "creates more captures to scroll through later. Something "
                 "around 5 to 10 seconds suits most lectures."),
                ("2", "Capture Method",
                 "How you tell the app which part of the screen to grab. Mouse "
                 "Select lets you drag a rectangle over the area once the "
                 "recording starts. Coordinates shows X, Y, width and height "
                 "boxes so you can type an exact region. Full Window just grabs "
                 "the whole source, no questions asked."),
                ("3", "Source",
                 "The monitor or the open window to record from. The list shows "
                 "what's open right now, so if the lecture window is missing, "
                 "open it first and come back."),
                ("4", "Audio",
                 "Where the sound comes from. Pick your microphone for an "
                 "in-person lecture, or a System Audio (Loopback) device to "
                 "record what your PC itself is playing, which is the one you "
                 "want for online lectures."),
            ]),
            ("p",
             "While recording, two shortcuts are worth knowing: Ctrl+Enter "
             "grabs an extra snapshot right now, on top of the interval ones, "
             "and Enter stops the recording (it asks first, so you can't stop "
             "one by accident)."),
        ],
    ),
    (
        "After Recording",
        "What a finished session looks like in the workspace.",
        [
            ("figure", "Help Panel 4", "A freshly recorded session", [
                "When you stop a recording there's nothing left to do, the "
                "session is already filled in. Every snapshot became its own "
                "card in Screen OCR: the slide image on top, the text the app "
                "read off it underneath, and a timestamp showing when it "
                "appeared. The trash button deletes a capture you don't want, "
                "and the collapse button folds one away to save space.",
                "The Audio transcript panel has everything that was said, in "
                "order, with timestamps. Each chunk of speech sits level with "
                "the slide that was on screen at the time, and turning on "
                "“Scroll Sync” makes the two panels scroll together so you can "
                "follow the lecture through both at once.",
                "Both text panels start out as “Locked”, so a stray click can't "
                "mess anything up. Click “Locked” and it flips to “Editable”, "
                "letting you fix anything the app misread or misheard. "
                "Everything you type is saved automatically, no save button "
                "needed. The AI summary stays empty until you press "
                "“Summarize”, which has its own chapter.",
            ]),
        ],
    ),
    (
        "Session Properties",
        "View and edit a session's details.",
        [
            ("p",
             "Press “Properties” (or Ctrl+D) and the session's details open "
             "next to the workspace. This is where renaming, recategorising, "
             "duplicating and deleting live."),
            ("figure", "Help Panel 5", "The Properties panel", [
                ("1", "Session Name",
                 "Rename the session. The sidebar picks up the new name when "
                 "you save."),
                ("2", "Activity Category",
                 "Change what kind of class it was. This also changes the "
                 "colour stripe on its sidebar card."),
                ("3", "Module Category",
                 "Move the session to a different course or module."),
                ("4", "Dates",
                 "A little history of the session, just for reference: when it "
                 "was recorded, when it was last changed, and when its summary "
                 "and quiz were generated. You can't edit these."),
                ("5", "Delete and Duplicate",
                 "“Delete” removes the session and everything inside it, after "
                 "asking you to confirm. “Duplicate” makes a complete copy, "
                 "captures, summary, quiz and all, which is handy before making "
                 "big edits."),
            ]),
            ("p",
             "“Save” applies what you changed. “Close” puts the panel away "
             "without saving."),
        ],
    ),
    (
        "Summarization",
        "Turn a whole session into a tidy set of AI notes.",
        [
            ("p",
             "Once a session has content in it, the AI summary panel can boil "
             "the whole thing down, slides and speech together, into a compact "
             "set of revision notes. This one runs through Gemini, so it needs "
             "the API key from Settings."),
            ("figure", "Help Panel 6", "A generated summary", [
                ("1", "Summarize",
                 "Reads through the entire session and writes structured notes "
                 "with headings and key terms. It takes a few seconds. Run it "
                 "again whenever the session's content changes and you want "
                 "fresh notes; if you've edited the summary yourself in the "
                 "meantime, it asks before overwriting your version."),
                ("2", "Preview and Edit",
                 "Flips the summary between the nicely formatted view and the "
                 "raw text. In the raw view you can rewrite the notes however "
                 "you like, and your edits are saved with the session."),
            ]),
        ],
    ),
    (
        "Translate & Define",
        "Look up or translate any text you select.",
        [
            ("p",
             "Spotted a term you don't know, or a phrase in a language you "
             "don't speak? Highlight any text in any panel, right-click it, and "
             "ask Gemini about it on the spot. This works in both Local and API "
             "mode, it just needs the API key."),
            ("figure", "Help Panel 7", "The right-click lookup menu", [
                ("1", "Define",
                 "Asks for a short, plain explanation of the selected word or "
                 "phrase, taking into account the context it appeared in."),
                ("2", "Translate to",
                 "Opens a list of languages to translate the selection into. "
                 "Ten common ones are built in, and “Other…” at the bottom lets "
                 "you type any language you want."),
            ]),
            ("figure", "Help Panel 7.1", "A definition result", [
                ("1", "The result card",
                 "The answer pops up in a small card near your cursor, with the "
                 "text you selected shown above it for reference. “Copy” puts "
                 "the result on the clipboard, and the ✕ or Esc closes the "
                 "card."),
            ]),
            ("figure", "Help Panel 7.2", "A translation result", [
                ("1", "Translations",
                 "Translations look exactly the same, with the language you "
                 "picked shown in the title."),
            ]),
        ],
    ),
    (
        "Importing Media",
        "Bring a lecture you already have as a file into the app.",
        [
            ("p",
             "Already have the lecture as a file, like a downloaded video or a "
             "phone recording? Open the session it should go into and press "
             "“Import”. The app works through the file the same way it handles "
             "a live lecture: the audio is transcribed chunk by chunk, and if "
             "it's a video, frames are grabbed and read as slides too. Most "
             "common formats work, including mp3, wav, m4a, mp4, mkv and webm."),
            ("figure", "Help Panel 8", "The Import media dialog", [
                ("1", "Playback",
                 "A preview of your file. Press “Play” and drag the slider "
                 "around to find where the lecture actually begins."),
                ("2", "Start point",
                 "This line confirms where transcription will start from, so "
                 "you can skip intros, ads or dead air at the front of the "
                 "file."),
                ("3", "Transcribe from here",
                 "Starts the import from that spot. “Cancel” closes the dialog "
                 "without importing anything."),
            ]),
            ("figure", "Help Panel 8.1", "An import in progress", [
                ("1", "Progress",
                 "The footer shows how far through the file the app has got. "
                 "The session fills in as it goes, so you can watch the "
                 "captures appear one by one."),
                ("2", "Pause and Stop",
                 "“Pause” takes a break, and pressing it again continues. "
                 "“Stop” ends the import early but keeps everything done so "
                 "far. While an import is running the rest of the app is "
                 "locked, same as during a live recording."),
            ]),
        ],
    ),
    (
        "Quiz",
        "Generate a self-test from a session's content.",
        [
            ("p",
             "Press “Quiz” to test yourself on a session. The questions are "
             "written from the session's summary, so generate that first (the "
             "quiz page reminds you if you haven't). Like the other AI "
             "features, it needs the Gemini API key."),
            ("figure", "Help Panel 9", "The quiz start page", [
                ("1", "Generate Quiz",
                 "Writes a brand-new quiz from the session's content. Longer "
                 "sessions get more questions. If a quiz already exists you'll "
                 "also see “Review”, which shows your last attempt, and "
                 "“Retake”, which runs the same questions again. Generating "
                 "replaces the old quiz."),
            ]),
            ("figure", "Help Panel 9.1", "Generating the quiz", [
                "Generating takes a few seconds. While you wait, the page shows "
                "which Gemini model is busy writing your questions.",
            ]),
            ("figure", "Help Panel 9.2", "Answering a question", [
                "Questions are a mix of multiple choice and true or false. Pick "
                "your answer, then press Enter (or “Next”) to move on. Esc (or "
                "“Previous”) steps back if you change your mind, and the up and "
                "down arrow keys walk through the options.",
            ]),
            ("figure", "Help Panel 9.3", "The results review", [
                "At the end you get your score plus a card for every question, "
                "showing what you picked, what was right, and a short "
                "explanation of why. “Retake” runs the same quiz again and "
                "“Done” heads back to the start page. The quiz and your answers "
                "are saved with the session, so you can come back and review "
                "them any time.",
            ]),
        ],
    ),
    (
        "Getting a Gemini API Key",
        "Get a free key from Google AI Studio for the AI features.",
        [
            ("p",
             "Summary, Quiz and Translate / Define all run on Google's Gemini, "
             "and Gemini needs a key. The good news is there's a free tier and "
             "it's plenty for studying. Head to "
             '<a href="https://aistudio.google.com/api-keys" style="color:#c15f3c;">AI Studio</a>, '
             "sign in with any Google account, and follow the steps below."),
            ("figure", "Help Panel 10", "The AI Studio API Keys page", [
                ("1", "Create API key",
                 "On the API Keys page, press “Create API key” in the top "
                 "right."),
            ]),
            ("figure", "Help Panel 10.1", "Naming the key and picking a project", [
                ("1", "Choose a project",
                 "Every key has to belong to a Google Cloud project, which is "
                 "just Google's way of organising things. If the dropdown says "
                 "“No Cloud Projects Available”, open it."),
                ("2", "Create project",
                 "Then pick “Create project” and AI Studio makes one for you on "
                 "the spot. Give the key any name you like while you're here."),
            ]),
            ("figure", "Help Panel 10.2", "Creating the key", [
                ("1", "Create key",
                 "With the name and project filled in, press “Create key”. "
                 "Google generates a long code starting with “AIza”. That's "
                 "your key."),
            ]),
            ("figure", "Help Panel 10.3", "Copying the finished key", [
                ("1", "Copy key",
                 "Press “Copy key”. Then, back in LectureCapture, open Settings "
                 "(Ctrl+S), paste it into the “Google Gemini API Key” box, "
                 "press “Save”, and run “Test API Connection” to make sure "
                 "everything is talking to each other."),
            ]),
            ("p",
             "If something goes wrong later: “invalid API key” means the key "
             "was mistyped or deleted, so make a new one. “Daily limit "
             "reached” means you've used up the free tier for today, and it "
             "resets tomorrow. “Temporarily busy” is a hiccup on Google's end, "
             "just try again in a moment."),
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

        # Only the tile grid (page 0) is built now; each chapter page is built on
        # its first open. Building every page up front decoded all the chapter
        # screenshots on app launch — startup time and resident memory spent on
        # pages most runs never visit. Empty placeholders hold the stack slots so
        # a page's stack index always equals its chapter number.
        self._stack.addWidget(self._main_page())
        self._page_count = len(CHAPTERS) + 1  # chapters + the shortcuts page
        for _ in range(self._page_count):
            self._stack.addWidget(QWidget())
        self._built_pages: set[int] = set()
        self._api_key_index = 1 + next(
            i for i, (title, _blurb, _blocks) in enumerate(CHAPTERS)
            if title == API_KEY_CHAPTER_TITLE
        )

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
        body = QLabel(f"<b>{name}:</b> {text}")
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

    def _build_page(self, index: int) -> None:
        # Swap the placeholder in this stack slot for the real page, keeping the index.
        if index <= len(CHAPTERS):
            title, _blurb, blocks = CHAPTERS[index - 1]
            page, scroll = self._chapter_page(str(index), title, blocks)
        else:
            page, scroll = self._shortcuts_page()
        placeholder = self._stack.widget(index)
        self._stack.removeWidget(placeholder)
        placeholder.deleteLater()
        self._stack.insertWidget(index, page)
        self._page_scrolls[index] = scroll
        self._built_pages.add(index)

    def _open(self, index: int) -> None:
        if index != 0 and index not in self._built_pages:
            self._build_page(index)
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
