from dataclasses import dataclass
from datetime import datetime

@dataclass
class Session:
    name: str
    date_recorded: datetime
    date_modified: datetime
    activity_category: str
    length: int
    id: int | None = None
    module_category: str | None = None
    summary: str | None = None
    summary_generated_at: datetime | None = None
    # Saved quiz: JSON list of questions, the last score (correct count), a hash of the
    # source text it was generated from (to detect when content changed), and when it was
    # generated.
    quiz: str | None = None
    quiz_score: int | None = None
    quiz_source_hash: str | None = None
    quiz_generated_at: datetime | None = None
    # Per-question chosen answer indices from the last attempt (JSON list; null entries =
    # unanswered), so Review can highlight what the user got wrong. Backwards compatible:
    # quizzes saved before this column existed have it NULL -> Review shows only the key.
    quiz_answers: str | None = None

@dataclass
class OCRCapture:
    timestamp: float
    image_path: str
    extracted_text: str
    id: int | None = None
    session_id: int | None = None
    speech_text: str | None = None