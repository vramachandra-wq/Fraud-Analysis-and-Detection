import streamlit as st
from ui.session_state import reset_fraud_results


@st.dialog("🚫 Account Blacklisted")
def show_blacklist_dialog(acct_id: str) -> None:
    st.error(f"Account **{acct_id}** has been added to the blacklist.")
    if st.button("Close Window", use_container_width=True):
        st.rerun()


@st.dialog("🔓 Account Whitelisted")
def show_whitelist_dialog(acct_id: str) -> None:
    st.success(f"Account **{acct_id}** has been removed from the blacklist.")
    if st.button("Close Window", use_container_width=True):
        st.rerun()


@st.dialog("⚠️ Account is Blacklisted")
def show_vip_blacklist_blocked_dialog(acct_id: str) -> None:
    """
    Shown when an operator tries to add a blacklisted account to the VIP tier.
    Offers an inline option to whitelist the account first.
    """
    st.error(
        f"Account **{acct_id}** is currently on the blacklist and **cannot** be "
        "added to the VIP tier."
    )
    st.markdown(
        "To add this account to the VIP tier you must first remove it from the "
        "blacklist (whitelist it)."
    )
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔓 Whitelist & Continue to VIP", use_container_width=True, type="primary"):
            # Cleaned: Avoid direct DB calls in UI layer. 
            # Best practice is to route this through your business logic layer.
            from services.blacklist_service import whitelist_account 
            
            whitelist_account(acct_id)
            st.session_state["_pending_vip_after_whitelist"] = True
            st.success(f"Account **{acct_id}** has been whitelisted.")
            st.rerun()
            
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


@st.dialog("✅ VIP Override Authorized")
def show_manual_approve_success_dialog() -> None:
    st.success("The transaction has been approved and marked as **COMPLETED**.")
    # Shifted to primary type for definite call-to-action completion
    if st.button("Close and Return to Dashboard", use_container_width=True, type="primary"):
        reset_fraud_results()
        st.rerun()


@st.dialog("🚫 VIP Route Terminated")
def show_manual_reject_success_dialog() -> None:
    st.error("The transaction has been dropped and marked as **FAILED**.")
    if st.button("Close and Return to Dashboard", use_container_width=True):
        reset_fraud_results()
        st.rerun()

@st.dialog("⚠️ Confirm VIP Revocation")
def show_confirm_vip_revocation_dialog(acct_id: str) -> None:
    """Prompts the operator to confirm removing an account from the VIP tier."""
    st.warning(
        f"Are you sure you want to remove Account **{acct_id}** from the VIP tier? "
    )
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        # Destructive actions should use type="primary" to stand out, or you can style it with custom CSS
        if st.button("💥 Yes, Remove VIP Status", use_container_width=True, type="primary"):
            from services.vip_service import revoke_vip_status
            try:
                revoke_vip_status(acct_id)
                st.session_state[f"vip_revoked_{acct_id}"] = True
                st.rerun()
            except Exception as e:
                st.error(f"Failed to revoke VIP status: {e}")
                
    with col2:
        if st.button("Cancel & Keep VIP", use_container_width=True):
            st.rerun()