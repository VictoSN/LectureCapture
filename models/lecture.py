from dataclasses import dataclass
from datetime import datetime

@dataclass
class Session:
    name: str
    date_recorded: datetime
    date_modified: datetime
    session_category: str
    length: int
    id: int | None = None
    group_category: str | None = None
    summary: str | None = None
    summary_generated_at: datetime | None = None
    # Saved quiz: JSON list of questions, the last score (correct count), and a hash of
    # the source text it was generated from (to detect when the content has changed).
    quiz: str | None = None
    quiz_score: int | None = None
    quiz_source_hash: str | None = None

@dataclass
class OCRCapture:
    timestamp: float
    image_path: str
    extracted_text: str
    id: int | None = None
    session_id: int | None = None
    speech_text: str | None = None