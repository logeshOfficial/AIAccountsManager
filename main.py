import streamlit as st
from google_auth_oauthlib.flow import Flow
import db
import streamlit as st
import load_files_from_gdrive
import os

if st.button("delete"):
    DB_PATH = "/mount/src/invoices.db"
    if os.path.exists(DB_PATH):
        try:
            # 3. Perform the deletion
            os.remove(DB_PATH)
            st.success("Database deleted successfully!")
            # Optional: Rerun to refresh the UI state
            st.rerun()
        except Exception as e:
            st.error(f"Error occurred while deleting: {e}")
    else:
        st.warning("File not found. It might have already been deleted.")
        
def load_drive():
    # ================= CONFIG =================
    CLIENT_CONFIG = {
        "web": {
            "client_id": st.secrets["GOOGLE_CLIENT_ID"],
            "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [st.secrets["REDIRECT_URI"]],
        }
    }
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    # ================= HELPERS =================
    def start_oauth_flow():
        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=st.secrets["REDIRECT_URI"],
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",
            prompt="consent",
        )

        st.markdown("### 🔐 Google Login")
        st.markdown(f"[Click here to login with Google]({auth_url})")
        
    # -----------------------------
    # HANDLE OAUTH CALLBACK
    # -----------------------------
    def handle_callback():
        code = st.query_params.get("code")
            
        if not code:
            return None

        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=st.secrets["REDIRECT_URI"],
        )

        flow.fetch_token(code=code)
        st.session_state["creds"] = flow.credentials

        # Clean URL
        st.query_params.clear()
        st.rerun()

    # -----------------------------
    # LOAD CREDENTIALS SAFELY
    # -----------------------------
    def load_credentials():
        # 1️⃣ Session cache
        if "creds" in st.session_state:
            st.success("Welcome! You are logged in.")
            return st.session_state["creds"]
        return None

    # -----------------------------
    # LOGOUT (OPTIONAL BUT GOOD)
    # -----------------------------
    def logout():
        st.session_state.clear()
        st.success("Logged out")
        st.rerun()

    # -----------------------------
    # APP ENTRY POINT
    # -----------------------------

    creds = load_credentials()

    if not creds:
        handle_callback()
        start_oauth_flow()
        st.stop()
        
    if st.button("🚪 Logout"):
        logout()

    load_files_from_gdrive.initiate_drive(creds)
    
import streamlit as st
view = st.query_params.get("view", "home")

st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
st.sidebar.button("Chat_Bot", on_click=lambda: st.query_params.update({"view": "chat"}))
st.sidebar.button("Drive_Manager", on_click=lambda: st.query_params.update({"view": "drive"}))

if view == "home":
    st.title("🏠 Home")
    df = db.read_db()
    st.dataframe(df)
elif view == "chat":
    st.title("💬 Chat Bot")
elif view == "drive":
    st.title("📂 Drive Manager")
    load_drive()
