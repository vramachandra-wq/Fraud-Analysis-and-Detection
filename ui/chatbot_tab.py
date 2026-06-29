from __future__ import annotations
import streamlit as st
from ai.chatbot.pipeline import render_assistant_turn, run_query_pipeline, load_user_chat_history
from config.settings import GROQ_API_KEY, GROQ_SQL_MODEL, GROQ_SUMMARY_MODEL

# ── CSS Layout Constants ───────────────────────────────────────────────────

_CHAT_UI_CSS = """
<style>
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 0rem !important;
}
div[data-testid="stVContainer"] {
    overflow: visible !important;
    padding-bottom: 100px !important;
}
.chat-header {
    position: sticky;
    top: -1rem;
    z-index: 999;
    background-color: #0e1117;
    background: var(--background-color, #0e1117);
    padding: 1rem 0rem 1rem 0rem;
    border-bottom: 1px solid rgba(128,128,128,0.15);
    margin-bottom: 1.5rem;
    width: 100%;
}
div[data-testid="stChatMessage"] {
    padding: 0.6rem 0.8rem !important;
    border-radius: 12px !important;
    margin-bottom: 0.5rem !important;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: rgba(99, 102, 241, 0.06) !important;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: rgba(128, 128, 128, 0.05) !important;
}
.chat-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 35vh;
    opacity: 0.45;
    gap: 0.5rem;
}
</style>
"""

# ── Sidebar Engine Status Controls ─────────────────────────────────────────

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("---")
        st.markdown("### ⚙️ Analytics Engine")
        st.caption("**Provider:** Groq Cloud Infrastructure")
        st.caption(f"**SQL Model:** `{GROQ_SQL_MODEL}`")
        st.caption(f"**Summary Model:** `{GROQ_SUMMARY_MODEL}`")
        st.markdown("---")
        st.markdown("### 🔌 Connection Status")
        if GROQ_API_KEY:
            st.success("Groq Pipeline: Connected")
        else:
            st.error("Groq Pipeline: Key Missing")
        st.markdown("---")
        
        # User Isolated Session Clear Button
        if st.button("🗑️ Clear Chat History", use_container_width=True, key="clear_chat_btn"):
            current_user_key = st.session_state.get("user_key")
            if current_user_key:
                from database.connection import get_pooled_connection, release_pooled_connection
                conn = get_pooled_connection()
                try:
                    with conn.cursor() as cursor:
                        # Clear records belonging exclusively to the current user
                        cursor.execute("DELETE FROM curated.chatbot_history WHERE user_key = %s;", (int(current_user_key),))
                    conn.commit()
                except Exception as e:
                    print(f"Failed to truncate personal chat database partition: {e}")
                finally:
                    release_pooled_connection(conn)
            
            st.session_state.messages = []
            st.rerun()

# ── Chronological User-Isolated History Rendering ──────────────────────────

def _render_history(chat_container) -> None:
    with chat_container:
        if not st.session_state.messages:
            st.markdown(
                '<div class="chat-empty-state">'
                '<div class="icon">💬</div>'
                "<p>No messages yet.<br/>Ask a question below to get started.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg.get("role", "assistant")):
                if msg.get("role") != "assistant":
                    st.markdown(msg.get("content", ""))
                    continue
                # Safely delegates history rendering down to the unified turn controller
                render_assistant_turn(msg, df_key_suffix=str(idx))

# ── Main Entrypoint View Tab Controller ────────────────────────────────────

def render_chatbot_tab() -> None:
    # Inject CSS layers instantly
    st.markdown(_CHAT_UI_CSS, unsafe_allow_html=True)

    current_user_key = st.session_state.get("user_key")

    # Strict multi-user isolation check during initialization
    if "messages" not in st.session_state or not st.session_state.messages:
        if current_user_key:
            st.session_state.messages = load_user_chat_history(current_user_key)
        else:
            st.session_state.messages = []

    # Build Workspace Header
    _render_sidebar()
    st.markdown(
        '<div class="chat-header">'
        '<span style="font-size: 1.2rem; font-weight: 700; color: white;">💳 Banking Transactions Analytics</span>'
        '<br/>'
        '<span style="font-size: 0.85rem; opacity: 0.65; display: inline-block; margin-top: 0.2rem;">'
        'Ask anything about transactions, accounts, fraud patterns, and more.'
        '</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Render Active Canvas
    chat_container = st.container()
    _render_history(chat_container)

    # Process New Questions safely
    if user_query := st.chat_input("Ask anything about your transactions…"):
        st.session_state.messages.append({"role": "user", "content": user_query})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_query)
        run_query_pipeline(user_query, chat_container)