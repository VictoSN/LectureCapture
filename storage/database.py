import sqlite3
import os
import shutil

from models.lecture import Session, OCRCapture
from datetime import datetime
from pathlib import Path

class Storage:
    def __init__(self) -> None:
        # Get %APPDATA% path
        app_data = os.environ['APPDATA']
        self.base_dir = os.path.join(app_data, 'LectureCapture')
        os.makedirs(self.base_dir, exist_ok=True) # Create directory

        # Directory for sound effects
        sound_effects_dir = Path(self.base_dir) / 'sound_effects'
        sound_effects_dir.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite
        db_path = os.path.join(self.base_dir, 'database.db')
        self.conn = sqlite3.connect(db_path)

        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA foreign_keys = ON") # Enable foreign keys
        self.create_table()

    def create_table(self) -> None:
        self.cursor.execute("""
                            CREATE TABLE IF NOT EXISTS session(
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT NOT NULL, 
                                session_category TEXT NOT NULL, 
                                group_category TEXT,
                                date_recorded TEXT NOT NULL, 
                                date_modified TEXT NOT NULL, 
                                length INTEGER NOT NULL,
                                summary TEXT,
                                summary_generated_at TEXT
                            )
                            """)

        self.cursor.execute("""
                            CREATE TABLE IF NOT EXISTS ocrcapture(
                                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                timestamp REAL NOT NULL, 
                                image_path TEXT NOT NULL, 
                                extracted_text TEXT NOT NULL,
                                speech_text TEXT,
                                session_id INTEGER NOT NULL, 
                                FOREIGN KEY(session_id) REFERENCES session(id) ON DELETE CASCADE
                            )
                            """)
        self.conn.commit()

    def create_session(self, session: Session) -> int:
        # Convert to strings
        session.date_modified = session.date_modified.isoformat()
        session.date_recorded = session.date_recorded.isoformat()
        session.summary_generated_at = session.summary_generated_at.isoformat() if session.summary_generated_at else None

        self.cursor.execute(
            "INSERT INTO session (name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session.name, session.session_category, session.group_category, session.date_recorded, session.date_modified, session.length, session.summary, session.summary_generated_at)
        )

        self.conn.commit()

        # Get new id and create session's folder
        last_id = self.cursor.lastrowid
        file_path = Path(self.base_dir) / 'sessions' / str(last_id) /'captures'
        file_path.mkdir(parents=True, exist_ok=True)
        session.id = last_id
        return last_id 

    def _parse_datetime(self, value) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None

    def _row_to_session(self, row) -> Session:
        # Convert the strings into datetime & guard for nulls
        return Session(
            name=row[1],
            date_recorded=self._parse_datetime(row[4]),
            date_modified=self._parse_datetime(row[5]),
            session_category=row[2],
            length=row[6],
            id=row[0],
            group_category=row[3],
            summary=row[7],
            summary_generated_at=self._parse_datetime(row[8])
        )

    def get_all_sessions(self) -> list[Session]:
        self.cursor.execute("SELECT id, name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at FROM session")
        return [self._row_to_session(session) for session in self.cursor.fetchall()]        

    def get_session(self, id: int) -> Session:
        self.cursor.execute("SELECT id, name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at FROM session WHERE id = ?", (id,))
        row = self.cursor.fetchone()
        return self._row_to_session(row) if row else None

    def update_session(self, session: Session) -> None:
        self.cursor.execute(
            "UPDATE session SET name = ?, session_category = ?, group_category = ?, date_recorded = ?, date_modified = ?, length = ?, summary = ?, summary_generated_at = ? WHERE id = ?", 
            (
                session.name,
                session.session_category,
                session.group_category,
                session.date_recorded.isoformat() if isinstance(session.date_recorded, datetime) else session.date_recorded,
                datetime.now().isoformat(), # Always now
                session.length,
                session.summary,
                session.summary_generated_at.isoformat() if isinstance(session.summary_generated_at, datetime) else session.summary_generated_at,
                session.id
            )
        )

        self.conn.commit()
    
    def delete_session(self, id: int) -> None:
        file_path = Path(self.base_dir) / 'sessions' / str(id)
        
        if file_path.exists():
            shutil.rmtree(file_path)

        self.cursor.execute("DELETE FROM session WHERE id = ?", (id,))
        self.conn.commit()
    
    def create_ocr_capture(self, capture: OCRCapture) -> int:        
        self.cursor.execute(
            "INSERT INTO ocrcapture (timestamp, image_path, extracted_text, speech_text, session_id) VALUES (?, ?, ?, ?, ?)",
            (capture.timestamp, capture.image_path, capture.extracted_text, capture.speech_text, capture.session_id)
        )

        self.conn.commit()

        # Get new id and set it to the current capture's id
        last_id = self.cursor.lastrowid
        capture.id = last_id
        return last_id 

    def _row_to_ocrcapture(self, row) -> OCRCapture:
        # Convert the strings into datetime & guard for nulls
        return OCRCapture(
            timestamp=row[1],
            image_path=row[2],
            extracted_text=row[3],
            speech_text=row[4],
            id=row[0],
            session_id=row[5]
        )

    def get_captures_by_session(self, session_id: int) -> list[OCRCapture]:
        self.cursor.execute("SELECT id, timestamp, image_path, extracted_text, speech_text, session_id FROM ocrcapture WHERE session_id = ?", (session_id,))
        return [self._row_to_ocrcapture(captures) for captures in self.cursor.fetchall()]        

    def update_extracted_text(self, capture_id, extracted_text) -> None:
        self.cursor.execute(
            "UPDATE ocrcapture SET extracted_text = ? WHERE id = ?", (extracted_text, capture_id)
        )
        self.conn.commit()
    
    # Update without duplication bug (Used by updating the text field)
    def update_speech_text(self, capture_id, speech_text) -> None:
        self.cursor.execute(
            "UPDATE ocrcapture SET speech_text = ? WHERE id = ?", (speech_text, capture_id)
        )
        
        self.conn.commit()
    
    # Append without deleting the previous (Used by the audio worker thread)
    def append_speech_text(self, capture_id, speech_text) -> None:
        self.cursor.execute(
            "UPDATE ocrcapture SET speech_text = COALESCE(speech_text, '') || ? WHERE id = ?", (speech_text, capture_id)
        )
        
        self.conn.commit()

    def get_group_categories(self) -> list[str]:
        self.cursor.execute("SELECT DISTINCT group_category FROM session WHERE group_category IS NOT NULL")
        return [row[0] for row in self.cursor.fetchall()]

    def search_sessions(self, name, session_category, group_category) -> list[Session]:
        query = "SELECT id, name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at FROM session WHERE 1=1"
        params = []
        
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
            
        if session_category and session_category != "All":
            query += " AND session_category = ?"
            params.append(session_category)
            
        if group_category and group_category != "All":
            query += " AND group_category = ?"
            params.append(group_category)
        
        self.cursor.execute(query, params)
        return [self._row_to_session(captures) for captures in self.cursor.fetchall()]

    def duplicate_sessions(self, id) -> Session:
        # Copy session and captures in database
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO session (name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at)
            SELECT name || ' (Copy)', session_category, group_category, ?, ?, length, summary, summary_generated_at
            FROM session WHERE id = ?
        """, (now, now, id))

        duplicated_id = self.cursor.lastrowid

        self.cursor.execute("""
            INSERT INTO ocrcapture (timestamp, image_path, extracted_text, speech_text, session_id)
            SELECT timestamp, image_path, extracted_text, speech_text, ?
            FROM ocrcapture WHERE session_id = ?
        """, (duplicated_id, id))

        self.conn.commit()    
        
        # Copy images folder
        src = Path(self.base_dir) / 'sessions' / str(id)
        dst = Path(self.base_dir) / 'sessions' / str(duplicated_id)
        
        if src.exists():
            shutil.copytree(src, dst)
            
        return self.get_session(duplicated_id)
    
    def close(self) -> None:
        self.conn.close()