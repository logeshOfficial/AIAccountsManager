import streamlit as st
import db
import oauth
   
view = st.query_params.get("view", "home")

st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
st.sidebar.button("Chat_Bot", on_click=lambda: st.query_params.update({"view": "chat"}))
st.sidebar.button("Drive_Manager", on_click=lambda: st.query_params.update({"view": "drive"}))

if view == "home":
    st.title("🏠 Home")

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

    df = db.read_db()
    st.dataframe(df)
    
elif view == "chat":
    st.title("💬 Chat Bot")
    
elif view == "drive":
    st.title("📂 Drive Manager")
    oauth.load_drive()
