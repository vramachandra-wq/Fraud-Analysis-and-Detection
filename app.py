import secrets
import streamlit as st

# Database connector tracking credentials and dynamics
from auth.db import get_user
from database.connection import get_pooled_connection, release_pooled_connection

from ui.session_state import init_session_state
from ui.transaction_tab import render_transaction_tab
from ui.vip_management_tab import render_vip_management_tab
from ui.chatbot_tab import render_chatbot_tab
from ui.admin_control_panel import render_admin_control_panel

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
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .stChatInputContainer { padding-bottom: 1rem; }
    hr { margin-top: 1.5rem; margin-bottom: 1.5rem; }
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
if "user_key" not in st.session_state:
    st.session_state.user_key = None
if "custom_role_name" not in st.session_state:
    st.session_state.custom_role_name = None
if "current_session_token" not in st.session_state:
    st.session_state.current_session_token = None

if "perms" not in st.session_state:
    st.session_state.perms = {"trans": False, "vip": False, "bot": False}

# ── 1. URL SESSION RECOVERY LAYER (Runs immediately on refresh/load) ─────────
if not st.session_state.authenticated and "session" in st.query_params:
    url_token = st.query_params["session"]
    
    conn = get_pooled_connection()
    try:
        with conn.cursor() as cursor:
            # Check the DB for an active tracking record matching this URL string
            cursor.execute("""
                SELECT s.user_key, s.username, u.custom_role_name, 
                       u.has_access_transactions, u.has_access_vip_hub, u.has_access_chatbot
                FROM curated.user_sessions s
                JOIN curated.users u ON s.user_key = u.user_key
                WHERE s.session_token = %s AND s.session_status = 'ACTIVE'
                LIMIT 1;
            """, (url_token,))
            row = cursor.fetchone()
            
            if row:
                # Session verified successfully! Repopulate memory variables
                st.session_state.authenticated = True
                st.session_state.user_key = row[0]
                st.session_state.username = row[1]
                st.session_state.custom_role_name = row[2]
                st.session_state.current_session_token = url_token
                st.session_state.perms = {
                    "trans": row[3],
                    "vip": row[4],
                    "bot": row[5]
                }
            else:
                # If token is dead or invalid, clear out toxic URL string parameters
                st.query_params.clear()
    except Exception as e:
        print(f"Failed token session auto-recovery: {e}")
    finally:
        release_pooled_connection(conn)

# ── 2. HEARTBEAT UPDATE LOGIC (Runs on active user tab interactions) ─────────
if st.session_state.authenticated and st.session_state.current_session_token:
    conn = get_pooled_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE curated.user_sessions SET last_heartbeat = NOW() WHERE session_token = %s;",
                (st.session_state.current_session_token,)
            )
        conn.commit()
    except Exception:
        pass
    finally:
        release_pooled_connection(conn)


# ─────────────────────────────────────────────────────────────
# Login Page Layout
# ─────────────────────────────────────────────────────────────
def render_login_page():
    st.title("🔒 Login")
    st.write("Please log in to access the Banking Fraud Detection Application.")

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter username").strip()
        password = st.text_input("Password", type="password", placeholder="Enter password")
        submit_button = st.form_submit_button("Log In", use_container_width=True)

        if submit_button:
            db_user = get_user(username)
            
            if db_user and isinstance(db_user, dict):
                user_pwd = db_user.get("password")
                user_name = db_user.get("username")
                role_name = db_user.get("custom_role_name")
                perm_trans = db_user.get("has_access_transactions", False)
                perm_vip = db_user.get("has_access_vip_hub", False)
                perm_bot = db_user.get("has_access_chatbot", False)
                
                fetched_user_key = db_user.get("user_key")

                # Verify credentials
                if password == user_pwd:
                    if fetched_user_key is None:
                        st.error("❌ Authentication Error: 'user_key' column missing from database fetch payload.")
                        return

                    secure_token = secrets.token_urlsafe(32)
                    
                    conn = get_pooled_connection()
                    try:
                        with conn.cursor() as cursor:
                            # ── 🛠️ NEW: STALE SESSION CLEANUP LAYER ──────────────────
                            # Look for any existing 'ACTIVE' session for this specific user.
                            # If found, set its logout_time to its last_heartbeat and mark it as 'CRASHED'.
                            cursor.execute("""
                                UPDATE curated.user_sessions 
                                SET logout_time = last_heartbeat,
                                    session_status = 'CRASHED'
                                WHERE user_key = %s AND session_status = 'ACTIVE';
                            """, (int(fetched_user_key),))
                            
                            # ── 📥 CREATE NEW SESSION ──────────────────────────────
                            cursor.execute("""
                                INSERT INTO curated.user_sessions (user_key, username, login_time, last_heartbeat, session_status, session_token)
                                VALUES (%s, %s, NOW(), NOW(), 'ACTIVE', %s);
                            """, (int(fetched_user_key), str(user_name), secure_token))
                        conn.commit()
                    except Exception as e:
                        st.error(f"Failed to record session track: {e}")
                        return
                    finally:
                        release_pooled_connection(conn)

                    # Initialize application session states cleanly
                    st.session_state.authenticated = True
                    st.session_state.user_key = int(fetched_user_key)
                    st.session_state.username = user_name
                    st.session_state.custom_role_name = role_name
                    st.session_state.current_session_token = secure_token
                    
                    st.session_state.perms = {
                        "trans": perm_trans,
                        "vip": perm_vip,
                        "bot": perm_bot
                    }

                    # Append session tracking string directly to browser address parameters bar
                    st.query_params["session"] = secure_token
                    st.success("Access Granted!")
                    st.rerun()
                else:
                    st.error("Invalid Username or Password. Please try again.")
            else:
                st.error("Invalid Username or Password. Please try again.")

# ─────────────────────────────────────────────────────────────
# Main Application Layout Engine
# ─────────────────────────────────────────────────────────────
if not st.session_state.authenticated:
    render_login_page()
else:
    # 1. EVALUATE STRINGS FOR WORKSPACE VIEWS FIRST
    tabs_to_build = []

    if st.session_state.perms["trans"]:
        tabs_to_build.append("🔍 Bank Transaction Fraud Engine")

    if st.session_state.perms["vip"]:
        tabs_to_build.append("👑 Premium Accounts Hub")

    if st.session_state.perms["bot"]:
        tabs_to_build.append("💬 AI Data Analyst Assistant")

    # Master Rule: If root system admin, always append Admin Control Panel string
    is_system_admin = (st.session_state.username == "admin")
    if is_system_admin:
        tabs_to_build.append("⚙️ Admin Control Panel")

    # 2. Render Sidebar UI elements cleanly
    st.sidebar.title("FinGuard Platform")
    st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
    st.sidebar.write(f"Role Group: **{st.session_state.custom_role_name}**")

    if st.sidebar.button("Log Out", use_container_width=True):
        # Graceful database log status closeoff
        if st.session_state.current_session_token:
            conn = get_pooled_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE curated.user_sessions 
                        SET logout_time = NOW(), session_status = 'LOGOUT' 
                        WHERE session_token = %s;
                    """, (st.session_state.current_session_token,))
                conn.commit()
            except Exception as e:
                print(f"Failed to close session on logout: {e}")
            finally:
                release_pooled_connection(conn)

        # Clean browser URL and local memory buffers entirely
        st.query_params.clear()
        st.session_state.clear()
        st.rerun()

    # 3. Mount Native Navigation Controller Option
    if tabs_to_build:
        st.sidebar.write("---")
        selected_dashboard = st.sidebar.radio(
            "Switch Tabs", 
            options=tabs_to_build,
            index=0,
            key="app_navigation_selector"
        )
        
        # ─────────────────────────────────────────────────────────
        # VIEW RENDERING ROUTER
        # ─────────────────────────────────────────────────────────
        if selected_dashboard == "🔍 Bank Transaction Fraud Engine":
            render_transaction_tab()

        elif selected_dashboard == "👑 Premium Accounts Hub":
            render_vip_management_tab()

        elif selected_dashboard == "💬 AI Data Analyst Assistant":
            render_chatbot_tab()

        elif selected_dashboard == "⚙️ Admin Control Panel" and is_system_admin:
            render_admin_control_panel()
            
    else:
        st.warning("Your account currently has no active dashboard permissions assigned. Please contact your administrator.")