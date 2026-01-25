import streamlit as st
from google_auth_oauthlib.flow import Flow
import load_files_from_gdrive
from googleapiclient.discovery import build
from app_logger import get_logger

logger = get_logger(__name__)

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
    user_email = st.session_state.get("user_email", "System")
    logger.info(f"User logging out: {user_email}", extra={"user_id": user_email})
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
        # 1. Check if already handled by a concurrent run
        if "creds" in st.session_state:
            st.query_params.clear()
            st.rerun()
            
        try:
            flow = Flow.from_client_config(
                _client_config(),
                scopes=_scopes(),
                redirect_uri=st.secrets["REDIRECT_URI"],
            )
            flow.fetch_token(code=code)
            st.session_state["creds"] = flow.credentials
            
            # 2. Fetch and store user email for tenant isolation
            try:
                oauth2 = build("oauth2", "v2", credentials=flow.credentials)
                info = oauth2.userinfo().get().execute()
                email = (info or {}).get("email", "")
                st.session_state["user_email"] = email
                logger.info(f"User logged in successfully: {email}", extra={"user_id": email})
            except Exception as e:
                logger.error(f"Failed to fetch user email after login: {e}")
                st.session_state["user_email"] = ""

            st.query_params.clear()
            st.rerun()
        except Exception as e:
            # 3. Defensive check: if creds appeared during the attempt, just rerun
            if "creds" in st.session_state:
                st.query_params.clear()
                st.rerun()
            
            logger.error(f"OAuth token exchange failed: {e}")
            st.error(f"Authentication failed: {e}. Please click the login link again.")
            st.query_params.clear()
            st.stop()

    # -----------------------------
    # GENERATE AUTH URL
    # -----------------------------

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