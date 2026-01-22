import streamlit as st
from typing import Optional

def get_logged_in_user() -> str:
    """Returns the email of the currently logged-in user."""
    return st.session_state.get("user_email", "")

def is_admin() -> bool:
    """Checks if the currently logged-in user has administrative privileges."""
    user_email = get_logged_in_user().strip().lower()
    admin_email = st.secrets.get("admin_email", "").strip().lower()
    
    if not user_email or not admin_email:
        return False
        
    return user_email == admin_email

def require_login():
    """Halts execution if the user is not logged in."""
    if not get_logged_in_user():
        st.warning("Please log in to continue.")
        st.stop()

def require_admin():
    """Halts execution if the user is not an admin."""
    require_login()
    if not is_admin():
        st.error("Access Denied: This operation requires administrator privileges.")
        st.stop()
