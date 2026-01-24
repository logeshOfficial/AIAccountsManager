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
    """Main entry point for the Chat Bot view with Conversational Memory."""
    
    st.title("🤖 AI Invoice Assistant")
    st.caption("Ask questions, generate charts, or request Excel reports. I remember our conversation!")
    
    # 1. Login Check
    user_email = ensure_user_login()
    
    # 2. Initialize Session State for Chat History
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    # 3. Display Chat History
    for i, message in enumerate(st.session_state.messages):
        label = "user" if message.type == "human" else "assistant"
        with st.chat_message(label):
            st.markdown(message.content)
            # If the stored message has additional metadata (like a chart), display it
            if hasattr(message, "additional_kwargs"):
                chart = message.additional_kwargs.get("chart")
                if chart: st.plotly_chart(chart, use_container_width=True, key=f"hist_chart_{i}")
                file = message.additional_kwargs.get("file")
                if file and os.path.exists(file):
                    label = "📥 Download Excel" if file.endswith(".xlsx") else "📥 Download Chart"
                    with open(file, "rb") as f:
                        st.download_button(label=label, data=f, file_name=os.path.basename(file), key=f"hist_dl_{i}_{os.path.basename(file)}")
                
                chart_file = message.additional_kwargs.get("chart_file")
                if chart_file and os.path.exists(chart_file):
                    with open(chart_file, "rb") as f:
                        st.download_button(label="📥 Download Interactive Chart", data=f, file_name=os.path.basename(chart_file), key=f"hist_dl_chart_{i}_{os.path.basename(chart_file)}")

    # 4. Chat Input
    if query := st.chat_input("What would you like to know?"):
        # Display User Message
        with st.chat_message("user"):
            st.markdown(query)
        
        # Add to history
        st.session_state.messages.append(HumanMessage(content=query))
        
        # 5. Run Agent
        with st.spinner("🤖 Agent is thinking..."):
            result = agent_manager.run_agent(query, user_email, history=st.session_state.messages[:-1])
            
            # --- 🤖 A. Display Assistant Response ---
            # The agent returns the full updated message list. We want the NEW AIMessage.
            new_msgs = [m for m in result["messages"] if isinstance(m, AIMessage) and m not in st.session_state.messages]
            
            for i, ai_msg in enumerate(new_msgs):
                with st.chat_message("assistant"):
                    st.markdown(ai_msg.content)
                    
                    # Store chart/file in message metadata for persistence
                    ai_msg.additional_kwargs = {}
                    
                    # --- 📊 B. Display Generated Chart ---
                    chart_data = result.get("generated_chart")
                    if chart_data:
                        st.plotly_chart(chart_data, use_container_width=True, key=f"new_chart_{i}_{datetime.now().timestamp()}")
                        ai_msg.additional_kwargs["chart"] = chart_data
                    
                    # --- 💾 C. Provide Download Link ---
                    file_path = result.get("generated_file")
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            st.download_button(
                                label="📥 Download Excel Report",
                                data=f,
                                file_name=os.path.basename(file_path),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"new_dl_{i}_{os.path.basename(file_path)}"
                            )
                        ai_msg.additional_kwargs["file"] = file_path
                    
                    # --- 📊 D. Provide Chart Download Link ---
                    chart_file = result.get("generated_chart_file")
                    if chart_file and os.path.exists(chart_file):
                        with open(chart_file, "rb") as f:
                            st.download_button(
                                label="📥 Download Interactive Chart",
                                data=f,
                                file_name=os.path.basename(chart_file),
                                mime="text/html",
                                key=f"new_dl_chart_{i}_{os.path.basename(chart_file)}"
                            )
                        ai_msg.additional_kwargs["chart_file"] = chart_file
                
                st.session_state.messages.append(ai_msg)

            # --- 🔍 D. Source Data Expander ---
            df = result.get("invoices_df")
            if df is not None and not df.empty:
                with st.expander(f"View {len(df)} Matched Records"):
                    cols_to_show = ["invoice_number", "invoice_date", "vendor_name", "total_amount", "description"]
                    st.dataframe(df[[c for c in cols_to_show if c in df.columns]], width="stretch")
