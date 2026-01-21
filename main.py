import streamlit as st
import db
import oauth
import chat_bot

st.set_page_config(page_title="Invoices AI Manager", layout="wide")
   
view = st.query_params.get("view", "home")

st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
st.sidebar.button("Chat_Bot", on_click=lambda: st.query_params.update({"view": "chat"}))
st.sidebar.button("Drive_Manager", on_click=lambda: st.query_params.update({"view": "drive"}))

if view == "home":
    st.title("🏠 Home")

    # Allow login directly from Home page
    if "creds" not in st.session_state:
        oauth.ensure_google_login(show_ui=True)

    user_email = st.session_state.get("user_email", "")
    admin_email = st.secrets.get("admin_email", "").strip().lower()
    is_admin = (user_email or "").strip().lower() == admin_email

    if user_email:
        st.caption(f"Signed in as: {user_email}" + (" (admin)" if is_admin else ""))
    else:
        st.warning("Could not fetch your Google email. Please logout and login again.")

    with st.expander("⚠️ Danger zone", expanded=False):
        st.write("This will permanently delete the local invoices database and all stored invoices.")
        confirm_drop = st.checkbox("I understand — delete invoices.db", value=False)
        recreate = st.checkbox("Recreate empty DB after delete", value=True)

        if st.button("🗑️ Drop invoices DB", disabled=not confirm_drop, type="primary"):
            ok, msg = db.drop_invoices_db(recreate=recreate)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # Security: normal users only see their own rows; admin sees everything.
    df = db.read_db(user_id=user_email, is_admin=is_admin)
    st.dataframe(df)
    
elif view == "chat":
    chat_bot.run_chat_interface()
    
    
elif view == "drive":
    st.title("📂 Drive Manager")
    oauth.load_drive()
