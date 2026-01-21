import streamlit as st
import os

def show_log_viewer():
    """
    Displays the contents of app.log in a scrollable text area.
    Useful for debugging in Streamlit Cloud.
    """
    st.markdown("### 📜 Application Logs")
    
    log_file = "app.log"
    
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            # Read last 500 lines to avoid massive load
            lines = f.readlines()
            logs = "".join(lines[-500:])
            
        st.text_area("Last 500 Log Entries", logs, height=400)
        
        if st.button("Refresh Logs"):
            st.rerun()
            
        if st.button("Clear Logs", type="secondary"):
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("")
            st.success("Logs cleared.")
            st.rerun()
    else:
        st.warning("No log file found.")
