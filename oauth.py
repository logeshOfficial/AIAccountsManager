import streamlit as st
from google_auth_oauthlib.flow import Flow
import db
import streamlit as st
import load_files_from_gdrive

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