import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from io import BytesIO
import pandas as pd
import google_auth_oauthlib

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
        client_config=CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=CLIENT_CONFIG["web"]["redirect_uris"][0],
    )
    auth_url, state = flow.authorization_url(prompt="consent")
    st.write(state)
    st.session_state["oauth_flow"] = flow
    st.markdown(f"[Login with Google]({auth_url})")

# ================= APP LOGIC =================
st.title("🌟 Google Drive OAuth Example")

# 1️⃣ Check if user is returning with ?code=XYZ
if "code" in st.query_params:
    code = st.query_params["code"]  # Query params are lists
    st.write(code)
    # if "oauth_flow" not in st.session_state:
    #     st.warning("OAuth flow missing. Please login again.")
    #     start_oauth_flow()
    #     st.stop()
        
    flow = st.session_state["oauth_flow"]
    flow.fetch_token(code=code)
    st.session_state["creds"] = flow.credentials
    st.success("✅ Google login successful!")

# 2️⃣ If already logged in
if "creds" in st.session_state:
    st.write("Welcome! You are logged in.")

    # Logout button
    if st.button("Logout"):
        st.session_state.pop("creds")
        st.session_state.pop("oauth_flow", None)
        st.rerun()

# 3️⃣ If not logged in yet
elif "creds" not in st.session_state:
    start_oauth_flow()
