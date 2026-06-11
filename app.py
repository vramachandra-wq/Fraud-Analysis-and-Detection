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
init_session_state()

# ── App title ──────────────────────────────────────────────────────────────
st.title("Banking Transaction Fraud Detection")

# ── Tabs ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "🔍 Bank Transaction Fraud Detection",
    "👑 VIP Accounts Management",
    "💬 Analytics Chatbot",
])

with tab1:
    render_transaction_tab()

with tab2:
    render_vip_management_tab()

with tab3:
    render_chatbot_tab()
