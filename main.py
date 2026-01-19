# import streamlit as st
# from google_auth_oauthlib.flow import Flow
# import db
# import streamlit as st

# def load_drive():
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
#     SCOPES = ["https://www.googleapis.com/auth/drive"]

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

#         st.session_state["creds"] = flow.credentials

#         # Clean URL
#         st.query_params.clear()
#         st.rerun()

#     # -----------------------------
#     # LOAD CREDENTIALS SAFELY
#     # -----------------------------
#     def load_credentials():
#         # 1️⃣ Session cache
#         if "creds" in st.session_state:
#             st.success("Welcome! You are logged in.")
#             return st.session_state["creds"]

#         return None

#     # -----------------------------
#     # LOGOUT (OPTIONAL BUT GOOD)
#     # -----------------------------
#     def logout():
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

    
#     if st.button("🚪 Logout"):
#         logout()

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
import requests
from urllib.parse import urlencode

# Configuration (Ensure these are set in your .streamlit/secrets.toml)
CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["REDIRECT_URI"]

def get_authorization_url():
    # Google Authorization Endpoint
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        # Added openid and email scopes for Google
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account"
    }
    return f"{base_url}?{urlencode(params)}"

def exchange_code_for_token(code):
    # Google Token Endpoint
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    response = requests.post(token_url, data=data)
    return response.json()

# Main app logic
st.title("Google OAuth Example")

# 1. Handle the redirect from Google (when 'code' is in the URL)
if "code" in st.query_params:
    code = st.query_params["code"]
    
    if "access_token" not in st.session_state:
        token_data = exchange_code_for_token(code)
        if "access_token" in token_data:
            st.session_state.access_token = token_data.get("access_token")
            # Google also provides an id_token for user info
            st.session_state.id_token = token_data.get("id_token")
        else:
            st.error("Authentication failed. Check your secrets.")
    
    # Clean up the URL by removing the code and rerun
    st.query_params.clear()
    st.rerun()

# 2. Display Login or Authenticated UI
if "access_token" in st.session_state:
    st.success("Authenticated with Google!")
    st.write(f"Access Token: `{st.session_state.access_token[:15]}...`")
    
    if st.button("Logout"):
        del st.session_state.access_token
        st.rerun()
else:
    st.write("Welcome! Please sign in to continue.")
    auth_url = get_authorization_url()
    # Using a link styled as a button
    st.link_button("Login with Google", auth_url)
    
    
    
    
    
# from streamlit_oauth import OAuth2Component

# oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL)
# result = oauth2.authorize_button("Login", REDIRECT_URI, SCOPE)

# if result:
#     st.write(result)