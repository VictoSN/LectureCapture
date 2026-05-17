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
    summary_generated_at: str | None = None
    
@dataclass
class OCRCapture:
    timestamp: float
    image_path: str
    extracted_text: str
    session_id: int | None = None
    id: int | None = None
    
@dataclass
class TranscriptChunk:
    start_timestamp: float
    end_timestamp: float
    extracted_text: str
    session_id: int | None = None
    id: int | None = None