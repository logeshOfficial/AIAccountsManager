# import streamlit as st
# from google_auth_oauthlib.flow import Flow
# from googleapiclient.discovery import build
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# import db
# import json
# import load_files_from_gdrive


# import os
# import streamlit as st

# DB_PATH = "/mount/src/oauth_tokens.db"

# if st.button("delete_token_db"):
#     if os.path.exists(DB_PATH):
#         os.remove(DB_PATH)
#         st.success("✅ token.db deleted successfully")
#     else:
#         st.info("ℹ️ token.db not found")

# def load_drive():
#     # 👤 TEMP USER ID
#     # In production → use Auth0 / Streamlit auth user id
#     USER_ID = "default_user"

#     # ================= CONFIG =================
#     CLIENT_CONFIG = {
#         "web": {
#             "client_id": st.secrets["GOOGLE_CLIENT_ID"],
#             "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
#             "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#             "token_uri": "https://oauth2.googleapis.com/token",
#             "redirect_uris": [st.secrets["REDIRECT_URI"]],
#         }
#     }
#     SCOPES = [
#     "https://www.googleapis.com/auth/drive",
#     "https://www.googleapis.com/auth/drive.readonly",
#         ]

#     # ================= HELPERS =================
#     def start_oauth_flow():
#         flow = Flow.from_client_config(
#             CLIENT_CONFIG,
#             scopes=SCOPES,
#             redirect_uri=st.secrets["REDIRECT_URI"],
#         )

#         auth_url, _ = flow.authorization_url(
#             access_type="offline",
#             include_granted_scopes="false",
#             prompt="consent",
#         )

#         st.markdown("### 🔐 Google Login")
#         st.markdown(f"[Click here to login with Google]({auth_url})")
        
#     # -----------------------------
#     # HANDLE OAUTH CALLBACK
#     # -----------------------------
#     def handle_callback():
#         code = st.query_params.get("code")

#         if not code:
#             return None

#         flow = Flow.from_client_config(
#             CLIENT_CONFIG,
#             scopes=SCOPES,
#             redirect_uri=st.secrets["REDIRECT_URI"],
#         )

#         flow.fetch_token(code=code)
#         creds = flow.credentials

#         # ✅ STORE IN SQLITE
#         db.save_token(USER_ID, creds.to_json())

#         st.session_state["creds"] = creds

#         # Clean URL
#         st.query_params.clear()
#         st.rerun()

#     # -----------------------------
#     # LOAD CREDENTIALS SAFELY
#     # -----------------------------
#     def load_credentials():
#         # 1️⃣ Session cache
#         if "creds" in st.session_state:
#             return st.session_state["creds"]

#         # 2️⃣ SQLite
#         token_json = db.load_token(USER_ID)
#         st.write(token_json)
#         if token_json:
#             info = json.loads(token_json)

#             creds = Credentials.from_authorized_user_info(
#                 info=info,
#                 scopes=SCOPES,
#             )

#             if creds.expired and creds.refresh_token:
#                 creds.refresh(Request())
#                 db.save_token(USER_ID, creds.to_json())

#             st.session_state["creds"] = creds
#             return creds

#         return None

#     # -----------------------------
#     # LOGOUT (OPTIONAL BUT GOOD)
#     # -----------------------------
#     def logout():
#         db.delete_token(USER_ID)
#         st.session_state.clear()
#         st.success("Logged out")
#         st.rerun()

#     # -----------------------------
#     # APP ENTRY POINT
#     # -----------------------------

#     creds = load_credentials()

#     if not creds:
#         handle_callback()
#         start_oauth_flow()
#         st.stop()

#     # -----------------------------
#     # AUTHENTICATED AREA
#     # -----------------------------
#     st.success("✅ Logged in successfully")
    
#     if st.button("🚪 Logout"):
#         logout()

#     load_files_from_gdrive.initiate_drive(creds)
#     # # Example Google Drive call
#     # drive = build("drive", "v3", credentials=creds)
#     # files = drive.files().list(fields="files(name)").execute()

#     # st.write("📁 Your Drive files:")
#     # for f in files.get("files", []):
#     #     st.write("•", f["name"])

# import streamlit as st
# view = st.query_params.get("view", "home")

# st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
# st.sidebar.button("Chat_Bot", on_click=lambda: st.query_params.update({"view": "chat"}))
# st.sidebar.button("Drive_Manager", on_click=lambda: st.query_params.update({"view": "drive"}))

# if view == "home":
#     st.title("🏠 Home")
#     df = db.read_db()
#     st.dataframe(df)
# elif view == "chat":
#     st.title("💬 Chat Bot")
# elif view == "drive":
#     st.title("📂 Drive Manager")
#     load_drive()

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

SCOPES = ["https://www.googleapis.com/auth/drive"]

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
    
    st.write("state: ", state)
    st.session_state["oauth_state"] = state
    st.markdown(f"[Login with Google]({auth_url})")

# ---------------- CALLBACK ----------------
if "code" in st.query_params:
    try:
        code = st.query_params["code"]
        state = st.query_params.get("state")

        # if "oauth_state" not in st.session_state or state != st.session_state["oauth_state"]:
        #     st.error("Invalid OAuth state. Please login again.")
        #     st.stop()

        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=CLIENT_CONFIG["web"]["redirect_uris"][0],
            state=state,
        )

        flow.fetch_token(code=code)
        st.session_state["creds"] = flow.credentials
        st.success("✅ Logged in successfully")
        st.query_params.clear()
    
    except Exception as e:
        st.error(e)

# ---------------- LOGGED IN ----------------
if "creds" in st.session_state:
    st.success("Welcome! You are logged in.")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# ---------------- NOT LOGGED IN ----------------
else:
    start_login()