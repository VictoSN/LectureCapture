import sqlite3
import os
import shutil

from ..models.lecture import Session, OCRCapture, TranscriptChunk
from datetime import datetime
from pathlib import Path

class Storage:
    def __init__(self):
        # Get %APPDATA% path
        app_data = os.environ['APPDATA']
        self.base_dir = os.path.join(app_data, 'LectureCapture')
        os.makedirs(self.base_dir, exist_ok=True) # Create directory
        
        # Conntect to SQLite
        db_path = os.path.join(self.base_dir, 'database.db')
        self.conn = sqlite3.connect(db_path)
        
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA foreign_keys = ON") # Enable foreign keys
        self.create_table()
        
    def create_table(self):
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
                                extracted_text TEXT NOT NULL, 
                                image_path TEXT NOT NULL, 
                                session_id INTEGER NOT NULL, 
                                FOREIGN KEY(session_id) REFERENCES session(id) ON DELETE CASCADE
                            )
                            """)
        
        self.cursor.execute("""
                            CREATE TABLE IF NOT EXISTS transcriptchunk(
                                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                start_timestamp REAL NOT NULL, 
                                end_timestamp REAL NOT NULL, 
                                extracted_text TEXT NOT NULL, 
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
        file_path.mkdir(exist_ok=True)
        session.id = last_id
        return last_id 
        
    def _parse_datetime(self, value):
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
    
    def get_all_session(self) -> list[Session]:
        self.cursor.execute("SELECT id, name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at FROM session")
        return [self._row_to_session(session) for session in self.cursor.fetchall()]        

    def get_session(self, id: int) -> Session:
        self.cursor.execute("SELECT id, name, session_category, group_category, date_recorded, date_modified, length, summary, summary_generated_at FROM session WHERE id = ?", (id,))
        row = self.cursor.fetchone()
        return self._row_to_session(row) if row else None
    
    def update_session(self, session: Session):
        session.date_modified = session.date_modified.isoformat()
        session.date_recorded = session.date_recorded.isoformat()
        session.summary_generated_at = session.summary_generated_at.isoformat() if session.summary_generated_at else None

        self.cursor.execute(
            "UPDATE session SET name = ?, session_category = ?, group_category = ?, date_recorded = ?, date_modified = ?, length = ?, summary = ?, summary_generated_at = ? WHERE id = ?", 
            (session.name, session.session_category, session.group_category, session.date_recorded, session.date_modified, session.length, session.summary, session.summary_generated_at, session.id)
        )
        
        self.conn.commit()
    
    def delete_session(self, id: int):
        file_path = Path(self.base_dir) / 'sessions' / str(id)
        
        if file_path.exists():
            shutil.rmtree(file_path)
            
        self.cursor.execute("DELETE FROM session WHERE id = ?", (id,))
        self.conn.commit()
    
    def close(self):
        self.conn.close()