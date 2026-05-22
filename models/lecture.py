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
    
@dataclass
class OCRCapture:
    timestamp: float
    image_path: str
    extracted_text: str
    id: int | None = None
    session_id: int | None = None
    speech_text: str | None = None