import streamlit as st
from ui.session_state import init_session_state
from ui.transaction_tab import render_transaction_tab
from ui.vip_management_tab import render_vip_management_tab
from ui.chatbot_tab import render_chatbot_tab

# ── Page configuration ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bank Fraud Detection",
    page_icon="💳",
    layout="centered",
)

st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .stChatInputContainer { padding-bottom: 1rem; }
    hr { margin-top: 1rem; margin-bottom: 1rem; }
    </style>
""", unsafe_allow_html=True)

# ── Session state bootstrap ────────────────────────────────────────────────
# This now safely handles the "authenticated" state key as well
init_session_state()

# ── Login Page View ────────────────────────────────────────────────────────
def render_login_page():
    st.title("🔒 Admin Login")
    st.write("Please log in to access the Banking Fraud Detection dashboard.")
    
    # Using a form prevents Streamlit from rerunning on every keystroke
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter admin username")
        password = st.text_input("Password", type="password", placeholder="Enter admin password")
        submit_button = st.form_submit_button("Log In", use_container_width=True)
        
        if submit_button:
            if username == "admin" and password == "admin":
                st.session_state.authenticated = True
                st.success("Access Granted!")
                st.rerun()
            else:
                st.error("Invalid Username or Password. Please try again.")

# ── Main Application Switcher ──────────────────────────────────────────────
if not st.session_state.authenticated:
    render_login_page()
else:
    # App title displayed only after a successful login
    st.title("FinGuard Platform")
    
    # Sidebar logout controls
    st.sidebar.title("Navigation")
    st.sidebar.write(f"Logged in as: **admin**")
    if st.sidebar.button("Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

    # Dashboard Tabs
    tab1, tab2, tab3 = st.tabs([
        "🔍 Bank Transaction Fraud Detection Engine",
        "👑 Premium Accounts Hub",
        "💬 AI Data Analyst Assistant",
    ])

    with tab1:
        render_transaction_tab()

    with tab2:
        render_vip_management_tab()

    with tab3:
        render_chatbot_tab()