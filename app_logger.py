import logging
import datetime
from datetime import timezone, timedelta
import streamlit as st
import os
from typing import Optional

# IST is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

class SupabaseHandler(logging.Handler):
    """
    Custom logging handler that writes logs to a Supabase table.
    Captures the current Streamlit user_email if available.
    """
    def __init__(self):
        super().__init__()
        # Note: We initialize the client inside emit to handle streamlit context better
        # and ensure it's available when needed.

    def _get_supabase_client(self):
        from supabase import create_client
        url = st.secrets.get("supabase_url")
        key = st.secrets.get("supabase_key")
        if not url or not key:
            return None
        try:
            return create_client(url, key)
        except Exception:
            return None

    def emit(self, record):
        try:
            client = self._get_supabase_client()
            if not client:
                return

            msg = self.format(record)
            
            # Attempt to get user_id from Streamlit session
            try:
                user_id = st.session_state.get("user_email", "System")
                if not user_id:
                     user_id = "System"
            except Exception:
                user_id = "System"

            ts = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            
            data = {
                "timestamp": ts,
                "level": record.levelname,
                "name": record.name,
                "message": msg,
                "user_id": user_id
            }
            
            # Non-blocking fire-and-forget isn't easily built-in for the client,
            # but for a simple logger in a Streamlit app, this sync call is usually okay.
            client.table("logs").insert(data).execute()
        except Exception:
            # We don't want logger failures to crash the app
            pass

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger instance.
    Logs are written to Supabase via SupabaseHandler and printed to stdout.
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(message)s')
        
        # Supabase Handler
        supabase_handler = SupabaseHandler()
        supabase_handler.setFormatter(formatter)
        supabase_handler.setLevel(logging.INFO)
        
        # Console Handler (keep for cloud logs)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(console_formatter)
        stream_handler.setLevel(logging.INFO)
        
        logger.addHandler(supabase_handler)
        logger.addHandler(stream_handler)
        
    return logger
