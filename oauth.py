import streamlit as st
from google_auth_oauthlib.flow import Flow
import streamlit as st
import load_files_from_gdrive
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

def _client_config():
    return {
        "web": {
            "client_id": st.secrets["GOOGLE_CLIENT_ID"],
            "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [st.secrets["REDIRECT_URI"]],
        }
    }

def _scopes():
    # Drive + identity (to enforce per-user data isolation server-side)
    return [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/drive",
    ]

def logout():
    st.session_state.clear()
    st.success("Logged out")
    st.rerun()

def ensure_google_login(show_ui: bool = True):
    """
    Ensures the user is logged into Google and we have creds + user_email.
    If not logged in and show_ui=True, renders the login link on the current page.

    Returns:
        creds (or None)
    """
    if "creds" in st.session_state:
        return st.session_state["creds"]

    code = st.query_params.get("code")
    if code:
        flow = Flow.from_client_config(
            _client_config(),
            scopes=_scopes(),
            redirect_uri=st.secrets["REDIRECT_URI"],
        )

        flow.fetch_token(code=code)
        st.session_state["creds"] = flow.credentials

        # Fetch and store user email for tenant isolation
        try:
            oauth2 = build("oauth2", "v2", credentials=flow.credentials)
            info = oauth2.userinfo().get().execute()
            st.session_state["user_email"] = (info or {}).get("email", "")
        except Exception:
            # If we can't fetch email, keep empty; app will treat as not authenticated for data access.
            st.session_state["user_email"] = ""

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

    flow = Flow.from_client_config(
        _client_config(),
        scopes=_scopes(),
        redirect_uri=st.secrets["REDIRECT_URI"],
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
    )

    st.markdown("### 🔐 Google Login")
    st.markdown(f"[Click here to login with Google]({auth_url})")
    st.stop()

def load_drive():
    creds = ensure_google_login(show_ui=True)

    if st.button("🚪 Logout"):
        logout()

    load_files_from_gdrive.initiate_drive(creds)