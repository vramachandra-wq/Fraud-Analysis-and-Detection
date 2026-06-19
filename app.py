import streamlit as st

from auth.users import USERS

from ui.session_state import init_session_state
from ui.transaction_tab import render_transaction_tab
from ui.vip_management_tab import render_vip_management_tab
from ui.chatbot_tab import render_chatbot_tab


# ─────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Bank Fraud Detection",
    page_icon="💳",
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    .stChatInputContainer {
        padding-bottom: 1rem;
    }

    hr {
        margin-top: 1rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────────────────────

init_session_state()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "username" not in st.session_state:
    st.session_state.username = None

if "role" not in st.session_state:
    st.session_state.role = None


# ─────────────────────────────────────────────────────────────
# Login Page
# ─────────────────────────────────────────────────────────────

def render_login_page():
    st.title("🔒 Login")
    st.write(
        "Please log in to access the Banking Fraud Detection Application."
    )

    with st.form("login_form"):

        username = st.text_input(
            "Username",
            placeholder="Enter username"
        )

        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter password"
        )

        submit_button = st.form_submit_button(
            "Log In",
            use_container_width=True
        )

        if submit_button:

            if (
                username in USERS
                and password == USERS[username]["password"]
            ):

                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.role = USERS[username]["role"]

                st.success("Access Granted!")
                st.rerun()

            else:
                st.error(
                    "Invalid Username or Password. Please try again."
                )


# ─────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────

if not st.session_state.authenticated:

    render_login_page()

else:

    st.title("FinGuard Platform")

    role = st.session_state.role

    st.sidebar.title("Navigation")
    st.sidebar.write(
        f"Logged in as: **{st.session_state.username}**"
    )
    st.sidebar.write(
        f"Role: **{role.upper()}**"
    )

    if st.sidebar.button(
        "Log Out",
        use_container_width=True
    ):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.role = None
        st.rerun()

    # ─────────────────────────────────────────────────────────
    # ADMIN
    # ─────────────────────────────────────────────────────────

    if role == "admin":

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

    # ─────────────────────────────────────────────────────────
    # USER
    # ─────────────────────────────────────────────────────────

    elif role == "user":

        tab1, tab2 = st.tabs([
            "🔍 Bank Transaction Fraud Detection Engine",
            "💬 AI Data Analyst Assistant",
        ])

        with tab1:
            render_transaction_tab()

        with tab2:
            render_chatbot_tab()

    # ─────────────────────────────────────────────────────────
    # ANALYST
    # ─────────────────────────────────────────────────────────

    elif role == "analyst":

        st.subheader("💬 AI Data Analyst Assistant")
        render_chatbot_tab()

    else:

        st.error("Unauthorized role detected.")