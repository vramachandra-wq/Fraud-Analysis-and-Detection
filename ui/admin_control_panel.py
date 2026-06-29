import streamlit as st
from auth.db import get_all_users, create_user, update_user_permissions, delete_user

# ── 🚨 DIALOG SYSTEM MODALS ──────────────────────────────────────────────────

@st.dialog("🚨 Username Error")
def show_duplicate_username_modal(conflicting_username):
    st.markdown(f"The username **`{conflicting_username}`** is already registered in the database.")
    st.write("Please choose a different username or update the existing user's permissions instead.")
    if st.button("Close & Try Again", use_container_width=True):
        st.rerun()

@st.dialog("⚠️ Input Warning")
def show_warning_modal(message: str):
    st.warning(message)
    if st.button("Dismiss", use_container_width=True):
        st.rerun()

@st.dialog("🔒 Security Lock")
def show_safety_lock_modal(message: str):
    st.markdown(f"### Access Denied\n{message}")
    if st.button("Understand", use_container_width=True):
        st.rerun()

@st.dialog("🎉 Action Successful")
def show_success_modal(message: str):
    st.success(message)
    if st.button("Ok", use_container_width=True):
        st.rerun()

@st.dialog("🚨 Database Error")
def show_database_error_modal(message: str):
    st.error(message)
    if st.button("Close", use_container_width=True):
        st.rerun()


# ── ⚙️ FORM CALLBACK HANDLERS ───────────────────────────────────────────────

def handle_create_user():
    c_user = st.session_state.admin_create_user.strip()
    c_pass = st.session_state.admin_create_pass.strip()
    c_role = st.session_state.admin_create_role.strip()
    
    c_perm_trans = st.session_state.admin_create_chk_trans
    c_perm_vip = st.session_state.admin_create_chk_vip
    c_perm_bot = st.session_state.admin_create_chk_bot
    
    if not c_user or not c_pass or not c_role:
        st.session_state.admin_modal_trigger = ("WARNING", "All fields are mandatory to create an account!")
        return
        
    result = create_user(c_user, c_pass, c_role, c_perm_trans, c_perm_vip, c_perm_bot)
    
    if result == "SUCCESS":
        st.session_state.admin_modal_trigger = ("SUCCESS", f"Profile for '{c_user}' provisioned successfully!")
    elif result == "DUPLICATE":
        st.session_state.admin_modal_trigger = ("DUPLICATE", c_user)
    else:
        st.session_state.admin_modal_trigger = ("DATABASE_ERROR", "Could not write user record data to PostgreSQL storage.")

def handle_update_user():
    target_user = st.session_state.admin_edit_select
    e_role = st.session_state.admin_edit_role.strip()
    e_perm_trans = st.session_state.admin_edit_chk_trans
    e_perm_vip = st.session_state.admin_edit_chk_vip
    e_perm_bot = st.session_state.admin_edit_chk_bot
    
    if target_user == "admin":
        st.session_state.admin_modal_trigger = ("LOCK", "Safety lock triggered: Core System Admin settings cannot be changed or overridden.")
        return
    if not e_role:
        st.session_state.admin_modal_trigger = ("WARNING", "Please enter a Role Description before applying updates.")
        return
        
    if update_user_permissions(target_user, e_role, e_perm_trans, e_perm_vip, e_perm_bot):
        st.session_state.admin_modal_trigger = ("SUCCESS", f"Permissions matrix updated successfully for {target_user}!")
    else:
        st.session_state.admin_modal_trigger = ("DATABASE_ERROR", "Failed to modify storage layer cluster permission configurations.")

def handle_delete_user():
    del_target = st.session_state.admin_del_select
    if del_target == "admin":
        st.session_state.admin_modal_trigger = ("LOCK", "Safety Lock triggered: The Root Admin management account cannot be deactivated.")
        return
        
    if delete_user(del_target):
        # UI UPDATE: Modified text to specify deactivation over total deletion
        st.session_state.admin_modal_trigger = ("SUCCESS", f"Account credentials and access permissions for '{del_target}' have been deactivated.")
    else:
        st.session_state.admin_modal_trigger = ("DATABASE_ERROR", "Failed to complete transaction task deactivation route request.")


# ── 🖥️ MAIN TAB RENDERER ────────────────────────────────────────────────────

def render_admin_control_panel():
    # 🌟 Modal Router Interceptor
    if "admin_modal_trigger" in st.session_state and st.session_state.admin_modal_trigger:
        modal_type, context = st.session_state.admin_modal_trigger
        st.session_state.admin_modal_trigger = None  # Clear context target frame immediately
        
        if modal_type == "DUPLICATE":
            show_duplicate_username_modal(context)
        elif modal_type == "WARNING":
            show_warning_modal(context)
        elif modal_type == "LOCK":
            show_safety_lock_modal(context)
        elif modal_type == "SUCCESS":
            show_success_modal(context)
        elif modal_type == "DATABASE_ERROR":
            show_database_error_modal(context)

    st.title("Admin Control Panel")
    st.write("Manage Credentials, Roles and Dashboard Access to the Platform.")
    
    # Fresh structural directory fetch
    all_users = get_all_users()
    user_summary_table = []
    user_dropdown_options = []
    
    for u in all_users:
        user_dropdown_options.append(u["username"])
        
        allowed_views = []
        if u["has_access_transactions"]: allowed_views.append("Transactions")
        if u["has_access_vip_hub"]: allowed_views.append("VIP Hub")
        if u["has_access_chatbot"]: allowed_views.append("AI Chatbot")
        
        user_summary_table.append({
            "Username": u["username"],
            "Role Profile Name": u["custom_role_name"],
            "Permitted Dashboards": ", ".join(allowed_views) if allowed_views else "None"
        })
    
    st.table(user_summary_table)
    st.write("---")
    
    # Form 1: Provision / Create New User Account
    st.markdown("#### ➕ Add New Profile & Access Credentials")
    with st.form("create_user_profile_form", clear_on_submit=True):
        st.text_input("Username", placeholder="Enter username", key="admin_create_user")
        st.text_input("Password", type="password", placeholder="Enter password", key="admin_create_pass")
        st.text_input("Role Description Name", placeholder="e.g., Level-2 Analyst", key="admin_create_role")
        
        st.write("**Grant Access To:**")
        st.checkbox("Transaction Fraud Engine", value=True, key="admin_create_chk_trans")
        st.checkbox("Premium Accounts Hub", key="admin_create_chk_vip")
        st.checkbox("AI Data Analyst Assistant", key="admin_create_chk_bot")
        
        st.form_submit_button("Save New Account", use_container_width=True, on_click=handle_create_user)

    st.write("---")
    col_edit, col_del = st.columns(2)
    
    # Form 2: Modify Existing Permissions Matrix
    with col_edit:
        st.markdown("#### 🔄 Modify Permissions")
        with st.form("edit_permissions_form"):
            st.selectbox("Select Profile to Modify", options=user_dropdown_options, key="admin_edit_select")
            st.text_input("Update Role Title/Description", placeholder="e.g., Level-1 Analyst", key="admin_edit_role")
            
            st.write("**Adjust Access Permissions:**")
            st.checkbox("Transaction Fraud Engine", key="admin_edit_chk_trans")
            st.checkbox("Premium Accounts Hub", key="admin_edit_chk_vip")
            st.checkbox("AI Data Analyst Assistant", key="admin_edit_chk_bot")
            
            st.form_submit_button("Apply Configuration Updates", use_container_width=True, on_click=handle_update_user)

    # Form 3: Deactivate Access / Soft Delete Account
    with col_del:
        # UI UPDATE: Swapped title, warning text, and button text to read as account deactivation
        st.markdown("#### ❌ Deactivate Account Access")
        with st.form("delete_user_profile_form"):
            st.selectbox("Select Account to Deactivate", options=user_dropdown_options, key="admin_del_select")
            st.caption("⚠️ Note: Confirming this action revokes system access permissions immediately without removing database profile records.")
            st.form_submit_button("Deactivate User Profile", use_container_width=True, on_click=handle_delete_user)