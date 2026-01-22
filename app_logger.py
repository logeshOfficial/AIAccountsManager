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
    _client = None

    def __init__(self):
        super().__init__()

    def _get_supabase_client(self):
        if SupabaseHandler._client:
            return SupabaseHandler._client

        from supabase import create_client
        url = st.secrets.get("supabase_url")
        key = st.secrets.get("supabase_key")
        if not url or not key:
            return None
        try:
            SupabaseHandler._client = create_client(url, key)
            return SupabaseHandler._client
        except Exception:
            return None

    def emit(self, record):
        try:
            client = self._get_supabase_client()
            if not client:
                return

            msg = self.format(record)
            
            # Attempt to get session-specific info
            user_id = "System"
            session_id = "Unknown"
            
            try:
                # Capture User Email
                user_email = st.session_state.get("user_email")
                if user_email:
                    user_id = user_email
                
                # Capture Session ID to distinguish between different "System" users
                from streamlit.runtime.scriptrunner import get_script_run_ctx
                ctx = get_script_run_ctx()
                if ctx:
                    session_id = ctx.session_id
            except Exception:
                pass

            ts = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            
            data = {
                "timestamp": ts,
                "level": record.levelname,
                "name": record.name,
                "message": msg,
                "user_id": user_id,
                "session_id": session_id
            }
            
            # Stage 1: Try full insert with session_id
            try:
                client.table("logs").insert(data).execute()
            except Exception as e:
                # Stage 2: Fallback to basic insert (in case session_id column is missing)
                try:
                    basic_data = {k: v for k, v in data.items() if k != "session_id"}
                    client.table("logs").insert(basic_data).execute()
                    # If this works, we know the issue was session_id
                except Exception as e2:
                    # Stage 3: Complete failure - log to console for developer visibility
                    print(f"⚠️ Supabase Logging Error: {e2}")
        except Exception as e_outer:
            print(f"⚠️ Logger Critical Error: {e_outer}")

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
