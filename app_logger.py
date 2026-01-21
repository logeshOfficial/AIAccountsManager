import logging
import sqlite3
import datetime
import streamlit as st
import os

DB_LOG_PATH = "log.db"

def init_log_db():
    """Ensures the log database and table exist."""
    try:
        conn = sqlite3.connect(DB_LOG_PATH, check_same_thread=False)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                name TEXT,
                message TEXT,
                user_id TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to initialize log DB: {e}")

class SQLiteHandler(logging.Handler):
    """
    Custom logging handler that writes logs to a SQLite database.
    Captures the current Streamlit user_email if available.
    """
    def __init__(self):
        super().__init__()
        init_log_db()

    def emit(self, record):
        try:
            msg = self.format(record)
            
            # Attempt to get user_id from Streamlit session
            try:
                # We check for attribute error in case this runs outside strictly managed context
                user_id = st.session_state.get("user_email", "System")
                if not user_id:
                     user_id = "System"
            except Exception:
                user_id = "System"

            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            conn = sqlite3.connect(DB_LOG_PATH, check_same_thread=False)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO logs (timestamp, level, name, message, user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (ts, record.levelname, record.name, msg, user_id))
            conn.commit()
            conn.close()
        except Exception:
            self.handleError(record)

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger instance.
    Logs are written to 'log.db' via SQLiteHandler and printed to stdout.
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(message)s') # We store raw message, metadata is in columns
        
        # SQLite Handler
        sqlite_handler = SQLiteHandler()
        sqlite_handler.setFormatter(formatter)
        sqlite_handler.setLevel(logging.INFO)
        
        # Console Handler (keep for cloud logs)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(console_formatter)
        stream_handler.setLevel(logging.INFO)
        
        logger.addHandler(sqlite_handler)
        logger.addHandler(stream_handler)
        
    return logger
