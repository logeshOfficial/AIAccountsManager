import streamlit as st
import db
import chat_bot
import auth_utils
import oauth
from app_logger import get_logger

logger = get_logger(__name__)

def validate_environment():
    """Ensures all required secrets are present before starting the app."""
    required_keys = [
        "supabase_url", "supabase_key", 
        "openai_api_key", "gemini_api_key", "admin_email",
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REDIRECT_URI", "INPUT_DOCS"
    ]
    missing = [k for k in required_keys if not st.secrets.get(k)]
    
    if missing:
        st.error(f"❌ Critical Configuration Error: Missing secrets in secrets.toml: {', '.join(missing)}")
        st.info("💡 Please provide these keys in your Streamlit secrets/secrets.toml file.")
        st.stop()

validate_environment()

st.set_page_config(page_title="Invoices AI Manager", layout="wide")

logger.info("Application started")
   
view = st.query_params.get("view", "home")
logger.info(f"Current view: {view}")

st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
st.sidebar.button("Chat_Bot", on_click=lambda: st.query_params.update({"view": "chat"}))
st.sidebar.button("Drive_Manager", on_click=lambda: st.query_params.update({"view": "drive"}))

user_email = auth_utils.get_logged_in_user()
is_admin = auth_utils.is_admin()

st.sidebar.markdown("---")
if is_admin:
    if st.sidebar.checkbox("Show Logs", value=False):
        import admin_utils
        admin_utils.show_log_viewer()

st.sidebar.markdown("---")
with st.sidebar.expander("❓ Help & Guide"):
    st.markdown("""
    **1. Authenticate**: Sign in with Google to securely link your Drive.
    
    **2. Instant Provision**: Your folders are created automatically on login. Just drop your PDFs into `Input_docs` in Drive.
    
    **3. Converse & Automate**: Head to **Chat_Bot** and just talk:
    - *"Sync my drive"* (Autonomous data retrieval)
    - *"Total spent in 2024?"* (Granular investigation)
    - *"Visualize my grocery bills as a pie chart"* (Intelligent design)
    - *"Email the 2025 yearly report to finance"* (Professional delivery)
    """)

if view == "home":
    st.title("🏠 Home")

    # Allow login directly from Home page
    if "creds" not in st.session_state:
        oauth.ensure_google_login(show_ui=True)

    if user_email:
        st.caption(f"Signed in as: {user_email}" + (" (admin)" if is_admin else ""))
    else:
        st.warning("Could not fetch your Google email. Please logout and login again.")

    st.markdown("---")
    
    # Security: normal users only see their own rows; admin sees everything.
    df = db.read_db(user_id=user_email, is_admin=is_admin)
    
    if not df.empty:
        # --- Financial Snapshot ---
        col1, col2, col3 = st.columns(3)
        total_spent = df['total_amount'].sum()
        invoice_count = len(df)
        
        with col1:
            st.metric("Total Spent", f"${total_spent:,.2f}")
        with col2:
            st.metric("Matched Invoices", invoice_count)
        with col3:
            st.metric("System Health", "Optimal")
            
        st.write("### 📄 Recent Activity")
        cols_to_show = ["invoice_number", "invoice_date", "vendor_name", "total_amount", "description"]
        st.dataframe(df[[c for c in cols_to_show if c in df.columns]], width="stretch")
    else:
        st.info("👋 **Welcome to your New Intelligence Suite!**")
        st.markdown(f"""
        ### 🚀 Final Step: Upload your Invoices
        To start analyzing your data, please follow these simple steps:
        1. **Go to Google Drive.**
        2. Locate and open the folder: `{st.secrets.get('INPUT_DOCS', 'Input_Docs')}`.
        3. **Drag and Drop** your PDF invoices into that folder.
        4. Return here to the **Chat Bot** and say: *"Sync my drive"*.
        """)
        st.warning(f"⚠️ **Note:** The folder `{st.secrets.get('INPUT_DOCS', 'Input_Docs')}` was automatically created for you upon login.")
    
elif view == "chat":
    chat_bot.run_chat_interface()
    
    
elif view == "drive":
    st.title("📂 Drive Manager")
    oauth.load_drive()
