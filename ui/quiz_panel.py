"""The quiz workspace — a splitter sibling shown via show_panel("quiz"), like Properties.

Self-contained state machine over a QStackedWidget: intro → loading → answering →
results. main_window drives generation/persistence; this panel owns the answering and
review UI and emits `completed(score, total)` so the score can be saved.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QRadioButton, QButtonGroup, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence


class QuizPanel(QWidget):
    generate_requested = pyqtSignal()   # (re)generate from the session content
    exit_requested = pyqtSignal()       # leave the quiz (main_window confirms if needed)
    completed = pyqtSignal(int, int)    # score, total — so the score can be persisted

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("quizPanel")

        self._questions: list[dict] = []
        self._answers: list[int | None] = []
        self._index = 0
        self._option_group: QButtonGroup | None = None
        self._saved_questions: list[dict] = []
        self._saved_score = None
        self._saved_answers: list = []   # chosen option per question from the last attempt

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Quiz")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()
        self.exit_button = QPushButton("Exit")
        self.exit_button.setToolTip("Leave the quiz (Esc)")
        self.exit_button.clicked.connect(self.exit_requested)
        header.addWidget(self.exit_button)
        root.addLayout(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.stack.addWidget(self._build_intro_page())     # 0
        self.stack.addWidget(self._build_loading_page())   # 1
        self.stack.addWidget(self._build_quiz_page())      # 2
        self.stack.addWidget(self._build_results_page())   # 3

        # Enter = next / primary action, Esc = previous question (or leave the quiz).
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._kb_next)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._kb_next)   # numpad Enter
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._kb_prev)
        # Up/Down move (and select) the answer option while answering.
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self._kb_select(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=lambda: self._kb_select(1))

    # ---- pages -----------------------------------------------------------

    def _build_intro_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.addStretch()

        self.intro_message = QLabel("")
        self.intro_message.setObjectName("muted")
        self.intro_message.setWordWrap(True)
        self.intro_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.intro_message)

        row = QHBoxLayout()
        row.addStretch()
        self.review_button = QPushButton("Review")
        self.review_button.clicked.connect(self._review_existing)
        row.addWidget(self.review_button)
        self.retake_button = QPushButton("Retake")
        self.retake_button.clicked.connect(self._retake)
        row.addWidget(self.retake_button)
        self.generate_button = QPushButton("Generate Quiz")
        self.generate_button.clicked.connect(self.generate_requested)
        row.addWidget(self.generate_button)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return page

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch()
        msg = QLabel("Generating your quiz…")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size: 15px;")
        layout.addWidget(msg)
        hint = QLabel("Reading through the session and writing questions.")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.loading_engine = QLabel("")
        self.loading_engine.setObjectName("muted")
        self.loading_engine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_engine)
        layout.addStretch()
        return page

    def _build_quiz_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        layout.addWidget(self.progress_label)

        self.question_label = QLabel("")
        self.question_label.setWordWrap(True)
        self.question_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.question_label)

        self.options_container = QWidget()
        self.options_layout = QVBoxLayout(self.options_container)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.options_layout.setSpacing(8)
        layout.addWidget(self.options_container)

        layout.addStretch()

        nav = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setToolTip("Previous question (Esc)")
        self.prev_button.clicked.connect(self._prev)
        nav.addWidget(self.prev_button)
        nav.addStretch()
        self.next_button = QPushButton("Next")
        self.next_button.setToolTip("Next question (Enter)")
        self.next_button.clicked.connect(self._next)
        nav.addWidget(self.next_button)
        # No keyboard focus on the nav buttons so Enter/Esc only drive the shortcuts
        # (and don't double-fire by also activating a focused button).
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addLayout(nav)
        return page

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.score_label = QLabel("")
        self.score_label.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(self.score_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.review_container = QWidget()
        self.review_layout = QVBoxLayout(self.review_container)
        self.review_layout.setContentsMargins(0, 0, 0, 0)
        self.review_layout.setSpacing(10)
        scroll.setWidget(self.review_container)
        layout.addWidget(scroll)

        row = QHBoxLayout()
        row.addStretch()
        self.results_retake_button = QPushButton("Retake")
        self.results_retake_button.clicked.connect(self._retake)
        row.addWidget(self.results_retake_button)
        self.results_exit_button = QPushButton("Done")
        self.results_exit_button.clicked.connect(self.exit_requested)
        row.addWidget(self.results_exit_button)
        layout.addLayout(row)
        return page

    # ---- driven by main_window ------------------------------------------

    def configure_intro(self, has_saved: bool, last_score, total, content_changed: bool) -> None:
        """Show the start screen. If a quiz is saved, offer Review/Retake; if the source
        content changed since it was made, nudge the user to regenerate. The saved quiz
        itself is provided separately via set_saved_quiz()."""
        if has_saved:
            scored = last_score is not None
            parts = []
            if scored:
                pct = round(last_score / total * 100) if total else 0
                parts.append(f"Last score: {last_score}/{total} ({pct}%).")
            if content_changed:
                parts.append("This session's content has changed since the quiz was made — "
                             "regenerate for an up-to-date quiz.")
            else:
                parts.append("Review the saved quiz, retake it, or generate a fresh one.")
            self.intro_message.setText(" ".join(parts))
            self.review_button.setVisible(True)
            self.retake_button.setVisible(True)
            self.generate_button.setText("Regenerate")
        else:
            self.intro_message.setText("Generate a quiz from this session's transcript to test "
                                       "yourself on the material.")
            self.review_button.setVisible(False)
            self.retake_button.setVisible(False)
            self.generate_button.setText("Generate Quiz")
        self.stack.setCurrentIndex(0)

    def set_saved_quiz(self, questions: list, last_score, answers=None) -> None:
        """Hand the panel the saved quiz so Review/Retake work without regenerating.
        `answers` (optional) are the chosen option indices from the last attempt."""
        self._saved_questions = list(questions or [])
        self._saved_score = last_score
        self._saved_answers = list(answers) if answers else []

    def current_answers(self) -> list:
        """Chosen option index per question for the current attempt (None = unanswered)."""
        return list(self._answers)

    def set_loading(self) -> None:
        self.loading_engine.setText("")
        self.stack.setCurrentIndex(1)

    def set_generating_engine(self, model: str) -> None:
        self.loading_engine.setText(f"Using {model}")

    def show_error(self, message: str) -> None:
        self.intro_message.setText(message)
        self.stack.setCurrentIndex(0)

    def load_questions(self, questions: list) -> None:
        """Start a fresh attempt at the given questions."""
        self._questions = list(questions or [])
        self._answers = [None] * len(self._questions)
        self._index = 0
        self._show_question(0)
        self.stack.setCurrentIndex(2)

    def is_answering(self) -> bool:
        return self.stack.currentIndex() == 2

    # ---- keyboard --------------------------------------------------------

    def _kb_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 2:                              # answering → next / finish
            self._next()
        elif idx == 0:                            # intro → primary action
            self.generate_button.click()
        elif idx == 3:                            # results → done
            self.exit_requested.emit()

    def _kb_prev(self) -> None:
        if self.is_answering():                   # answering → previous question
            self._prev()
        else:                                     # elsewhere → leave the quiz
            self.exit_requested.emit()

    def _kb_select(self, delta: int) -> None:
        """Move the selected answer option by `delta` (and record it) while answering.
        From no selection, Down picks the first option and Up the last."""
        if not self.is_answering() or self._option_group is None:
            return
        buttons = self._option_group.buttons()
        if not buttons:
            return
        current = self._option_group.checkedId()
        if current < 0:
            new_id = 0 if delta > 0 else len(buttons) - 1
        else:
            new_id = max(0, min(len(buttons) - 1, current + delta))
        button = self._option_group.button(new_id)
        if button:
            # setChecked() doesn't fire idClicked, so record the answer ourselves.
            button.setChecked(True)
            self._on_option(new_id)

    # ---- intro actions ---------------------------------------------------

    def _retake(self) -> None:
        if self._saved_questions:
            self.load_questions(self._saved_questions)

    def _review_existing(self) -> None:
        if not self._saved_questions:
            return
        self._questions = list(self._saved_questions)
        # Use the saved per-question choices when we have a set that lines up with the
        # questions; otherwise (older quizzes saved before answers were stored) fall back
        # to showing just the answer key.
        have_answers = len(self._saved_answers) == len(self._questions)
        self._answers = list(self._saved_answers) if have_answers else [None] * len(self._questions)
        self._build_results(self._saved_score, show_user_answers=have_answers)
        self.stack.setCurrentIndex(3)

    # ---- answering -------------------------------------------------------

    def _show_question(self, idx: int) -> None:
        self._index = idx
        q = self._questions[idx]
        self.progress_label.setText(f"Question {idx + 1} of {len(self._questions)}")
        self.question_label.setText(q.get("question", ""))

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._option_group = QButtonGroup(self.options_container)
        for i, opt in enumerate(q.get("options", [])):
            radio = QRadioButton(str(opt))
            self._option_group.addButton(radio, i)
            if self._answers[idx] == i:
                radio.setChecked(True)
            self.options_layout.addWidget(radio)
        self._option_group.idClicked.connect(self._on_option)

        self.prev_button.setEnabled(idx > 0)
        self.next_button.setText("Finish" if idx == len(self._questions) - 1 else "Next")

    def _on_option(self, option_id: int) -> None:
        self._answers[self._index] = option_id

    def _prev(self) -> None:
        if self._index > 0:
            self._show_question(self._index - 1)

    def _next(self) -> None:
        if self._index < len(self._questions) - 1:
            self._show_question(self._index + 1)
        else:
            self._finish()

    def _finish(self) -> None:
        score = sum(
            1 for i, q in enumerate(self._questions)
            if self._answers[i] == q.get("correct_index")
        )
        self._build_results(score, show_user_answers=True)
        self.stack.setCurrentIndex(3)
        self.completed.emit(score, len(self._questions))

    # ---- results ---------------------------------------------------------

    def _build_results(self, score, show_user_answers: bool) -> None:
        total = len(self._questions)
        if score is None:
            self.score_label.setText(f"Quiz — {total} questions")
        else:
            pct = round(score / total * 100) if total else 0
            self.score_label.setText(f"You scored {score} / {total}  ({pct}%)")

        while self.review_layout.count():
            item = self.review_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for i, q in enumerate(self._questions):
            self.review_layout.addWidget(self._review_card(i, q, show_user_answers))
        self.review_layout.addStretch()

    def _review_card(self, idx: int, q: dict, show_user_answers: bool) -> QWidget:
        card = QFrame()
        card.setObjectName("quizCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        correct_idx = q.get("correct_index")
        user_idx = self._answers[idx] if idx < len(self._answers) else None
        options = q.get("options", [])

        head = QLabel(f"{idx + 1}. {q.get('question', '')}")
        head.setWordWrap(True)
        head.setStyleSheet("font-weight: 600;")
        layout.addWidget(head)

        for i, opt in enumerate(options):
            prefix, color = "", None
            if i == correct_idx:
                prefix, color = "✓ ", "#2e9e5b"
            elif show_user_answers and i == user_idx:
                prefix, color = "✗ ", "#d9534f"
            line = QLabel(f"{prefix}{opt}")
            line.setWordWrap(True)
            if color:
                line.setStyleSheet(f"color: {color};")
            else:
                line.setObjectName("muted")
            layout.addWidget(line)

        if show_user_answers and user_idx is None:
            skipped = QLabel("Not answered")
            skipped.setStyleSheet("color: #d9534f;")
            layout.addWidget(skipped)

        explanation = q.get("explanation")
        if explanation:
            exp = QLabel(str(explanation))
            exp.setWordWrap(True)
            exp.setObjectName("muted")
            exp.setStyleSheet("font-style: italic;")
            layout.addWidget(exp)
        return card
