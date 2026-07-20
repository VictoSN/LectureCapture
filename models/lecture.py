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
    quiz: str | None = None
    quiz_score: int | None = None
    quiz_source_hash: str | None = None
    quiz_generated_at: datetime | None = None
    quiz_answers: str | None = None

@dataclass
class OCRCapture:
    timestamp: float
    image_path: str
    extracted_text: str
    id: int | None = None
    session_id: int | None = None
    speech_text: str | None = None