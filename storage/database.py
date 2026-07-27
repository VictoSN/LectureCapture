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
        self._rename_legacy_columns()
        self._wipe_if_old_schema()
        self.create_table()

    def _rename_legacy_columns(self) -> None:
        """Rename legacy column names to current naming."""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session'")
        if not self.cursor.fetchone():
            return  # fresh database. create_table builds the current schema.
        self.cursor.execute("PRAGMA table_info(session)")
        columns = {row[1] for row in self.cursor.fetchall()}
        if "session_category" in columns and "activity_category" not in columns:
            self.cursor.execute(
                "ALTER TABLE session RENAME COLUMN session_category TO activity_category")
            self.conn.commit()
        self.cursor.execute("PRAGMA table_info(session)")
        columns = {row[1] for row in self.cursor.fetchall()}
        if "group_category" in columns and "module_category" not in columns:
            self.cursor.execute(
                "ALTER TABLE session RENAME COLUMN group_category TO module_category")
            self.conn.commit()

    def _wipe_if_old_schema(self) -> None:
        """Drop tables if the schema is pre-current (no migration needed)."""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session'")
        if not self.cursor.fetchone():
            return  # fresh database. Nothing to wipe.
        self.cursor.execute("PRAGMA table_info(session)")
        columns = {row[1] for row in self.cursor.fetchall()}
        if "quiz_generated_at" in columns and "module_category" in columns:
            return  # already on the current schema
        # Recent-enough schemas (have activity_category):
        # migrate by adding missing columns instead of wiping.
        if "activity_category" in columns:
            self._add_column_if_missing("session", "module_category", "TEXT")
            self._add_column_if_missing("session", "quiz", "TEXT")
            self._add_column_if_missing("session", "quiz_score", "INTEGER")
            self._add_column_if_missing("session", "quiz_source_hash", "TEXT")
            self._add_column_if_missing("session", "quiz_generated_at", "TEXT")
            self._add_column_if_missing("session", "quiz_answers", "TEXT")
            self.conn.commit()
            return
        # Truly ancient schema: wipe and rebuild.
        self.cursor.execute("DROP TABLE IF EXISTS ocrcapture")
        self.cursor.execute("DROP TABLE IF EXISTS session")
        self.conn.commit()
        sessions_dir = Path(self.base_dir) / "sessions"
        if sessions_dir.exists():
            shutil.rmtree(sessions_dir, ignore_errors=True)

    def create_table(self) -> None:
        self.cursor.execute("""
                            CREATE TABLE IF NOT EXISTS session(
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT NOT NULL,
                                activity_category TEXT NOT NULL,
                                module_category TEXT,
                                date_recorded TEXT NOT NULL,
                                date_modified TEXT NOT NULL,
                                length INTEGER NOT NULL,
                                summary TEXT,
                                summary_generated_at TEXT,
                                quiz TEXT,
                                quiz_score INTEGER,
                                quiz_source_hash TEXT,
                                quiz_generated_at TEXT,
                                quiz_answers TEXT
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

        # Index capture lookups by session + timestamp for efficient queries.
        self.cursor.execute("""
                            CREATE INDEX IF NOT EXISTS idx_ocrcapture_session
                            ON ocrcapture(session_id, timestamp)
                            """)
        # Add quiz_answers column without wiping (additive migration).
        self._add_column_if_missing("session", "quiz_answers", "TEXT")
        self.conn.commit()

    def _add_column_if_missing(self, table: str, column: str, coltype: str) -> None:
        self.cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in self.cursor.fetchall()}
        if column not in columns:
            self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    def create_session(self, session: Session) -> int:
        # Convert to strings
        date_recorded = session.date_recorded.isoformat()
        date_modified = session.date_modified.isoformat()
        summary_generated_at = session.summary_generated_at.isoformat() if session.summary_generated_at else None
        quiz_generated_at = session.quiz_generated_at.isoformat() if isinstance(session.quiz_generated_at, datetime) else session.quiz_generated_at

        # Quiz columns are carried too, so an imported/duplicated session keeps its quiz.
        self.cursor.execute(
            "INSERT INTO session (name, activity_category, module_category, date_recorded, date_modified, length, summary, summary_generated_at, quiz, quiz_score, quiz_source_hash, quiz_generated_at, quiz_answers) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session.name, session.activity_category, session.module_category, date_recorded, date_modified, session.length, session.summary, summary_generated_at, session.quiz, session.quiz_score, session.quiz_source_hash, quiz_generated_at, session.quiz_answers)
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
            activity_category=row[2],
            length=row[6],
            id=row[0],
            module_category=row[3],
            summary=row[7],
            summary_generated_at=self._parse_datetime(row[8]),
            quiz=row[9],
            quiz_score=row[10],
            quiz_source_hash=row[11],
            quiz_generated_at=self._parse_datetime(row[12]),
            quiz_answers=row[13],
        )

    def get_all_sessions(self) -> list[Session]:
        self.cursor.execute("SELECT id, name, activity_category, module_category, date_recorded, date_modified, length, summary, summary_generated_at, quiz, quiz_score, quiz_source_hash, quiz_generated_at, quiz_answers FROM session")
        return [self._row_to_session(session) for session in self.cursor.fetchall()]        

    def get_session(self, id: int) -> Session:
        self.cursor.execute("SELECT id, name, activity_category, module_category, date_recorded, date_modified, length, summary, summary_generated_at, quiz, quiz_score, quiz_source_hash, quiz_generated_at, quiz_answers FROM session WHERE id = ?", (id,))
        row = self.cursor.fetchone()
        return self._row_to_session(row) if row else None

    def update_session(self, session: Session) -> None:
        self.cursor.execute(
            "UPDATE session SET name = ?, activity_category = ?, module_category = ?, date_recorded = ?, date_modified = ?, length = ?, summary = ?, summary_generated_at = ? WHERE id = ?", 
            (
                session.name,
                session.activity_category,
                session.module_category,
                session.date_recorded.isoformat() if isinstance(session.date_recorded, datetime) else session.date_recorded,
                datetime.now().isoformat(), # Always now
                session.length,
                session.summary,
                session.summary_generated_at.isoformat() if isinstance(session.summary_generated_at, datetime) else session.summary_generated_at,
                session.id
            )
        )

        self.conn.commit()
    
    def save_quiz(self, session_id: int, quiz_json: str, source_hash: str) -> None:
        """Store a newly generated quiz, resetting score and answers."""
        self.cursor.execute(
            "UPDATE session SET quiz = ?, quiz_source_hash = ?, quiz_generated_at = ?, quiz_score = NULL, quiz_answers = NULL WHERE id = ?",
            (quiz_json, source_hash, datetime.now().isoformat(), session_id)
        )
        self.conn.commit()

    def update_quiz_result(self, session_id: int, score: int, answers_json: str) -> None:
        """Persist score and per-question answers for Review."""
        self.cursor.execute(
            "UPDATE session SET quiz_score = ?, quiz_answers = ? WHERE id = ?",
            (score, answers_json, session_id)
        )
        self.conn.commit()

    def delete_session(self, id: int) -> None:
        file_path = Path(self.base_dir) / 'sessions' / str(id)
        
        if file_path.exists():
            shutil.rmtree(file_path)

        self.cursor.execute("DELETE FROM session WHERE id = ?", (id,))
        self.conn.commit()
    
    def delete_all_sessions(self) -> None:        
        sessions_dir = Path(self.base_dir) / "sessions"

        if sessions_dir.exists():
            for item in sessions_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        self.cursor.execute("DELETE FROM session")
        self.cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('session', 'ocrcapture')")
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
        # Timeline order (panels display list order).
        self.cursor.execute("SELECT id, timestamp, image_path, extracted_text, speech_text, session_id FROM ocrcapture WHERE session_id = ? ORDER BY timestamp", (session_id,))
        return [self._row_to_ocrcapture(captures) for captures in self.cursor.fetchall()]        

    def get_latest_capture_before(self, session_id: int, timestamp: float) -> OCRCapture | None:
        # Most recent capture at or before timestamp (indexed).
        self.cursor.execute(
            "SELECT id, timestamp, image_path, extracted_text, speech_text, session_id "
            "FROM ocrcapture WHERE session_id = ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (session_id, timestamp)
        )
        row = self.cursor.fetchone()
        return self._row_to_ocrcapture(row) if row else None

    def get_earliest_capture(self, session_id: int) -> OCRCapture | None:
        # First captured slide in the session.
        self.cursor.execute(
            "SELECT id, timestamp, image_path, extracted_text, speech_text, session_id "
            "FROM ocrcapture WHERE session_id = ? ORDER BY timestamp ASC LIMIT 1",
            (session_id,)
        )
        row = self.cursor.fetchone()
        return self._row_to_ocrcapture(row) if row else None

    def delete_capture(self, capture_id: int) -> None:
        # Fetch image path before deleting so we can remove the file
        self.cursor.execute("SELECT image_path, session_id FROM ocrcapture WHERE id = ?", (capture_id,))
        row = self.cursor.fetchone()
        if row:
            image_path, session_id = row
            file_path = Path(self.base_dir) / 'sessions' / str(session_id) / 'captures' / image_path
            # Speech-only captures: empty image_path -> skip file unlink (avoids PermissionError).
            if image_path and file_path.is_file():
                file_path.unlink()

        self.cursor.execute("DELETE FROM ocrcapture WHERE id = ?", (capture_id,))
        self.conn.commit()

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

    def get_module_categories(self) -> list[str]:
        self.cursor.execute("SELECT DISTINCT module_category FROM session WHERE module_category IS NOT NULL")
        return [row[0] for row in self.cursor.fetchall()]

    def get_activity_categories(self) -> list[str]:
        """Distinct activity categories in use. Merged with built-in defaults by caller."""
        self.cursor.execute(
            "SELECT DISTINCT activity_category FROM session "
            "WHERE activity_category IS NOT NULL AND activity_category != ''"
        )
        return [row[0] for row in self.cursor.fetchall()]

    def search_sessions(self, name, activity_category, module_category) -> list[Session]:
        query = "SELECT id, name, activity_category, module_category, date_recorded, date_modified, length, summary, summary_generated_at, quiz, quiz_score, quiz_source_hash, quiz_generated_at, quiz_answers FROM session WHERE 1=1"
        params = []
        
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
            
        if activity_category and activity_category != "All":
            query += " AND activity_category = ?"
            params.append(activity_category)
            
        if module_category and module_category != "All":
            query += " AND module_category = ?"
            params.append(module_category)
        
        self.cursor.execute(query, params)
        return [self._row_to_session(captures) for captures in self.cursor.fetchall()]

    def duplicate_sessions(self, id) -> Session:
        # Copy session and captures in database
        now = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO session (name, activity_category, module_category, date_recorded, date_modified, length, summary, summary_generated_at, quiz, quiz_score, quiz_source_hash, quiz_generated_at, quiz_answers)
            SELECT name || ' (Copy)', activity_category, module_category, ?, ?, length, summary, summary_generated_at, quiz, quiz_score, quiz_source_hash, quiz_generated_at, quiz_answers
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