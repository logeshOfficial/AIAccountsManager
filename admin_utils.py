import streamlit as st
import pandas as pd
import os
from db import get_supabase_client

def show_log_viewer():
    """
    Displays the contents of the 'logs' table from Supabase in a structured dataframe.
    """
    st.markdown("### 📜 Application Logs (Supabase)")
    
    client = get_supabase_client()
    if not client:
        st.error("Supabase client not initialized. Check your secrets.")
        return

    try:
        # Query logs from Supabase
        response = client.table("logs").select("*").order("id", desc=True).limit(500).execute()
        df = pd.DataFrame(response.data)
        
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
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            if st.button("🗑️ Clear All Logs"):
                try:
                    # Delete all records from logs table
                    client.table("logs").delete().neq("id", -1).execute()
                    st.success("Logs cleared successfully from Supabase.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to clear logs from Supabase: {e}")
        else:
            st.info("Log database in Supabase is empty.")
            
    except Exception as e:
        st.error(f"Error reading logs from Supabase: {e}")
