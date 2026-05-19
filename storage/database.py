import sqlite3
import os
import shutil

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
                                group_category TEXT,
                                summary TEXT,
                                summary_generated_at TEXT, 
                                date_recorded TEXT NOT NULL, 
                                date_modified TEXT NOT NULL, 
                                session_category TEXT NOT NULL, 
                                length INTEGER NOT NULL
                            )
                            """)
        
        self.cursor.execute("""
                            CREATE TABLE IF NOT EXISTS ocrcapture(
                                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                timestamp REAL NOT NULL, 
                                image_path TEXT NOT NULL, 
                                extracted_text TEXT NOT NULL, 
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