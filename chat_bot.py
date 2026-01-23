import streamlit as st
import pandas as pd
from datetime import datetime
import auth_utils
import oauth
import llm_manager
import invoice_manager
from langchain_core.messages import AIMessage, HumanMessage
import agent_manager
import os
from app_logger import get_logger

logger = get_logger(__name__)

# ==============================================================================
# MAIN INTERFACE
# ==============================================================================

def ensure_user_login():
    """Checks login status and halts execution if not logged in."""
    user_email = auth_utils.get_logged_in_user()
    if not user_email:
        st.warning("Please log in to use the Chat Bot.")
        oauth.ensure_google_login(show_ui=True)
        # Re-check after potential login interaction
        user_email = auth_utils.get_logged_in_user()
        if not user_email:
            st.stop()
            
    return user_email

def run_chat_interface():
    """Main entry point for the Chat Bot view."""
    
    st.title("📊 AI Invoice Assistant (Agentic)")
    st.caption("Ask questions, generate charts, or request Excel reports.")
    
    # 1. Login Check
    user_email = ensure_user_login()
    
    # 2. Query Input
    query = st.text_input("Message", placeholder="E.g., 'Show me a graph of my expenses and email me a report.'")
    
    if st.button("Send", type="primary") and query:
        logger.info(f"User Interrogation: '{query}'")
        with st.spinner("🤖 Agent is working..."):
            # Run the Agentic Workflow
            result = agent_manager.run_agent(query, user_email)
            
            # --- 🤖 A. Display AI Answer ---
            st.markdown("### 🤖 Assistant Response")
            # Filter and display AI messages from the graph state
            for msg in result.get("messages", []):
                if isinstance(msg, AIMessage):
                    st.write(msg.content)
            
            # --- 📊 B. Display Generated Chart ---
            chart_data = result.get("generated_chart")
            if chart_data:
                st.markdown("### 📊 Visualization")
                st.plotly_chart(chart_data, use_container_width=True)
            
            # --- 💾 C. Provide Download Link ---
            file_path = result.get("generated_file")
            if file_path and os.path.exists(file_path):
                st.markdown("### 📑 Generated Report")
                with open(file_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Excel Report",
                        data=f,
                        file_name=os.path.basename(file_path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            # --- 🔍 D. Source Data Expander ---
            df = result.get("invoices_df")
            if df is not None and not df.empty:
                with st.expander(f"View {len(df)} Source Documents"):
                    cols_to_show = ["invoice_number", "invoice_date", "vendor_name", "total_amount", "description"]
                    # Show dataframe with relevant columns
                    st.dataframe(df[[c for c in cols_to_show if c in df.columns]], width="stretch")
