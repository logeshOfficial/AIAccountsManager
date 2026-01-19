import streamlit as st
import db
import oauth
   
view = st.query_params.get("view", "home")

st.sidebar.button("Home", on_click=lambda: st.query_params.update({"view": "home"}))
st.sidebar.button("Chat_Bot", on_click=lambda: st.query_params.update({"view": "chat"}))
st.sidebar.button("Drive_Manager", on_click=lambda: st.query_params.update({"view": "drive"}))

if view == "home":
    st.title("🏠 Home")
    df = db.read_db()
    st.dataframe(df)
    
elif view == "chat":
    st.title("💬 Chat Bot")
    
elif view == "drive":
    st.title("📂 Drive Manager")
    oauth.load_drive()
