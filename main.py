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
    # st.markdown(
    #     f"""<a href="{auth_url}" target="_self" style="text-decoration: none;">
    #         <button style="background-color: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;">
    #             Login with Google
    #         </button>
    #     </a>""", 
    #     unsafe_allow_html=True
    # )
    # st.markdown(f'<a href="{auth_url}" target="_self">Login with Google</a>', unsafe_allow_html=True)
    # Using a link styled as a button
    st.link_button("Login with Google", auth_url)
    
    