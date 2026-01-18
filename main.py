import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import db
import json


# 👤 TEMP USER ID
# In production → use Auth0 / Streamlit auth user id
USER_ID = "default_user"

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
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ================= HELPERS =================
def start_oauth_flow():
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=st.secrets["REDIRECT_URI"],
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
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
    creds = flow.credentials

     # ✅ STORE IN SQLITE
    db.save_token(USER_ID, creds.to_json())

    st.session_state["creds"] = creds

    # Clean URL
    st.query_params.clear()
    st.rerun()

# -----------------------------
# LOAD CREDENTIALS SAFELY
# -----------------------------
def load_credentials():
    # 1️⃣ Session cache
    if "creds" in st.session_state:
        return st.session_state["creds"]

    # 2️⃣ SQLite
    token_json = db.load_token(USER_ID)
    if token_json:
        info = json.loads(token_json)

        creds = Credentials.from_authorized_user_info(
            info=info,
            scopes=SCOPES,
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            db.save_token(USER_ID, creds.to_json())

        st.session_state["creds"] = creds
        return creds

    return None

# -----------------------------
# LOGOUT (OPTIONAL BUT GOOD)
# -----------------------------
def logout():
    db.delete_token(USER_ID)
    st.session_state.clear()
    st.success("Logged out")
    st.rerun()


# -----------------------------
# APP ENTRY POINT
# -----------------------------

st.title("Google OAuth – Streamlit (Reliable Version)")

creds = load_credentials()

if not creds:
    handle_callback()
    start_oauth_flow()
    st.stop()

# -----------------------------
# AUTHENTICATED AREA
# -----------------------------
st.success("✅ Logged in successfully")

if st.button("🚪 Logout"):
    logout()

# Example Google Drive call
drive = build("drive", "v3", credentials=creds)
files = drive.files().list(pageSize=5, fields="files(name)").execute()

st.write("📁 Your Drive files:")
for f in files.get("files", []):
    st.write("•", f["name"])

