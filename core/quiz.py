"""Gemini-generated revision quiz from a session's combined transcript.

JSON mode with a response schema, so the result is structured and auto-gradable
(multiple-choice + true/false). Runs off the GUI thread like SummarizeWorker, and is
gated on a Gemini key (there's no good local equivalent). The number of questions is
left to the model. It's told to scale to how much substantive material there is.
"""

import hashlib
import json

from PyQt6.QtCore import QThread, pyqtSignal


def source_hash(text: str) -> str:
    """Stable hash of the source text, stored with a saved quiz so we can tell when the
    session content has changed and offer to regenerate."""
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


_PROMPT = (
    "You are creating a self-test quiz to help a student revise the lecture material "
    "below. Generate as many high-quality questions as the material genuinely supports: "
    "scale the count to how much substantive content there is. A short snippet might "
    "warrant only 3-4 questions, an hour-long lecture 20 or more (hard cap 30). Do NOT "
    "pad with trivial, repetitive, or easily-guessed filler; only include questions a "
    "student could meaningfully answer from this material.\n"
    "Mix multiple-choice (type \"mcq\", exactly 4 plausible options) and true/false "
    "(type \"true_false\", options exactly [\"True\", \"False\"]). For each question, set "
    "correct_index to the 0-based index of the correct option and write a one-sentence "
    "explanation of why it is correct.\n\n"
    "Lecture material:\n"
)


def _valid(q: dict) -> bool:
    try:
        opts = q["options"]
        return (isinstance(opts, list) and len(opts) >= 2
                and 0 <= int(q["correct_index"]) < len(opts)
                and bool(str(q.get("question", "")).strip()))
    except Exception:
        return False


def generate_quiz(text: str, api_key: str, on_attempt=None) -> list[dict]:
    from google.genai import types
    from pydantic import BaseModel

    from core.gemini import generate

    class QuizQuestion(BaseModel):
        type: str
        question: str
        options: list[str]
        correct_index: int
        explanation: str

    response, _model = generate(
        api_key,
        _PROMPT + text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[QuizQuestion],
        ),
        on_attempt=on_attempt,
    )
    data = json.loads(response.text or "[]")
    return [q for q in data if _valid(q)]


class QuizWorker(QThread):
    done = pyqtSignal(object)   # list[dict] of questions
    failed = pyqtSignal(str)    # friendly error message
    attempting = pyqtSignal(str)  # pretty model name currently being tried

    def __init__(self, text: str, api_key: str) -> None:
        super().__init__()
        self._text = text
        self._api_key = api_key

    def run(self) -> None:
        try:
            from core.gemini import pretty_model
            questions = generate_quiz(
                self._text, self._api_key,
                on_attempt=lambda m: self.attempting.emit(pretty_model(m)),
            )
        except Exception as e:
            from core.api_errors import classify_api_error, status_message
            status = classify_api_error(e)
            self.failed.emit(status_message(status) if status != "other" else str(e))
            return
        if not questions:
            self.failed.emit("Couldn't generate a quiz from this session's content.")
            return
        self.done.emit(questions)
