import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

CLIENT_CONFIG = {
    "web": {
        "client_id": st.secrets["GOOGLE_CLIENT_ID"],
        "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [st.secrets["REDIRECT_URI"]],
    }
}

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

st.title("🌟 Google Drive OAuth (Correct)")

# ---------------- START LOGIN ----------------
def start_login():
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=CLIENT_CONFIG["web"]["redirect_uris"][0],
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    st.session_state["oauth_state"] = state
    st.markdown(f"[Login with Google]({auth_url})")

# ---------------- CALLBACK ----------------
if "code" in st.query_params:
    code = st.query_params["code"][0]
    state = st.query_params.get("state", [None])[0]

    if "oauth_state" not in st.session_state or state != st.session_state["oauth_state"]:
        st.error("Invalid OAuth state. Please login again.")
        st.stop()

    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=CLIENT_CONFIG["web"]["redirect_uris"][0],
        state=state,
    )

    flow.fetch_token(code=code)
    st.session_state["creds"] = flow.credentials
    
    # 🚨 FORCE REAL REDIRECT
    st.markdown(
        "<meta http-equiv='refresh' content='0; url=/' />",
        unsafe_allow_html=True
    )
    st.stop()

# ---------------- LOGGED IN ----------------
if "creds" in st.session_state:
    st.success("Welcome! You are logged in.")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# ---------------- NOT LOGGED IN ----------------
else:
    start_login()
