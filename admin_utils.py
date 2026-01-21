import streamlit as st
import sqlite3
import pandas as pd
import os

DB_LOG_PATH = "log.db"

def show_log_viewer():
    """
    Displays the contents of log.db in a structured dataframe.
    """
    st.markdown("### 📜 Application Logs (SQLite)")
    
    if not os.path.exists(DB_LOG_PATH):
        st.warning("No log database found yet.")
        return

    try:
        conn = sqlite3.connect(DB_LOG_PATH, check_same_thread=False)
        
        # Query logs
        df = pd.read_sql_query("SELECT id, timestamp, user_id, level, name, message FROM logs ORDER BY id DESC LIMIT 500", conn)
        conn.close()
        
        if not df.empty:
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                search_user = st.text_input("Filter by User Email")
            with col2:
                search_msg = st.text_input("Filter by Message")
                
            if search_user:
                df = df[df["user_id"].str.contains(search_user, case=False, na=False)]
            if search_msg:
                df = df[df["message"].str.contains(search_msg, case=False, na=False)]
            
            st.dataframe(df, width='stretch', hide_index=True)
            
            st.markdown("---")
            if st.button("🗑️ Clear All Logs"):
                try:
                    conn = sqlite3.connect(DB_LOG_PATH, check_same_thread=False)
                    cur = conn.cursor()
                    cur.execute("DELETE FROM logs")
                    conn.commit()
                    conn.close()
                    st.success("Logs cleared successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to clear logs: {e}")
        else:
            st.info("Log database is empty.")
            
    except Exception as e:
        st.error(f"Error reading log database: {e}")
