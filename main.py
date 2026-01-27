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

# st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
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
    **1. Login**: Sign in with Google to access your data.
    
    **2. Sync Data**: Go to **Drive_Manager** and click "Start Processing" to import invoices from Drive.
    
    **3. Analyze**: Go to **Chat_Bot** and ask questions like:
    - *"Total spent in 2024?"*
    - *"Show grocery invoices"*
    
    **4. Admin**: Admins can view logs below.
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

    with st.expander("⚠️ Danger zone", expanded=False):
        # 1. User Action: Delete OWN data
        st.write("**My Data**")
        if st.button("🗑️ Delete ALL my uploaded invoices"):
            ok, msg = db.delete_user_data(user_email)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
                
        # 2. Admin Action: Delete EVERYTHING
        if is_admin:
            st.markdown("---")
            st.write("**Admin: Global Reset**")
            st.write("This will permanently delete the ENTIRE invoices database for ALL users.")
            confirm_drop = st.checkbox("I understand — delete invoices.db", value=False)
            recreate = st.checkbox("Recreate empty DB after delete", value=True)

            if st.button("💣 Drop invoices DB", disabled=not confirm_drop, type="primary"):
                ok, msg = db.drop_invoices_db(recreate=recreate)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # Security: normal users only see their own rows; admin sees everything.
    df = db.read_db(user_id=user_email, is_admin=is_admin)
    
    if not df.empty:
        cols_to_show = ["invoice_number", "invoice_date", "vendor_name", "total_amount", "description", "user_id"]
        if not is_admin:
            cols_to_show.remove("user_id")
        st.dataframe(df[[c for c in cols_to_show if c in df.columns]], width="stretch")
    else:
        st.info("No invoices found. Go to Drive Manager to sync your data.")
    
elif view == "chat":
    chat_bot.run_chat_interface()
    
    
elif view == "drive":
    st.title("📂 Drive Manager")
    oauth.load_drive()
