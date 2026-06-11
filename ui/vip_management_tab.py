import streamlit as st
from database.account_repository import is_valid_account
from database.blacklist_repository import is_blacklisted, remove_from_blacklist
from services.vip_service import (
    fetch_vip_details,
    modify_vip_limits,
    provision_vip,
    VIPBlacklistedError,
)
from ui.dialogs import show_vip_blacklist_blocked_dialog


def render_vip_management_tab() -> None:
    st.header("VIP Account Rule Governance")
    st.markdown(
        "Query existing VIP Account limits from the database, modify limits, and update limits."
    )

    search_account_id = st.text_input("Enter Account ID", key="vip_mgmt_search_id")
    if not search_account_id.strip():
        return

    vip_data = fetch_vip_details(search_account_id)

    if vip_data:
        _render_existing_vip(search_account_id, vip_data)
    else:
        _render_new_vip_registration(search_account_id)


# ── Private helpers ────────────────────────────────────────────────────────

def _render_existing_vip(account_id: str, vip_data: dict) -> None:
    st.success(f"📊 Active VIP record located for Account: **{account_id}**")

    c1, c2 = st.columns(2)
    with c1:
        st.metric(
            "Current Amount Limit",
            f"${float(vip_data['amount_per_transaction_limit']):,}",
        )
    with c2:
        st.metric(
            "Current Per Day Transactions Limit",
            f"{vip_data['transactions_limit']} transactions",
        )

    st.markdown("---")
    st.subheader("Update Limits")

    with st.form(key="update_vip_limits_form"):
        new_amt_limit = st.number_input(
            "New Transaction Amount Limit ($)",
            min_value=0.0,
            value=float(vip_data["amount_per_transaction_limit"]),
            step=500.0,
        )
        new_vol_limit = st.number_input(
            "New Transaction Volume Limit (Daily)",
            min_value=1,
            value=int(vip_data["transactions_limit"]),
            step=1,
        )
        if st.form_submit_button("Save and Replace Limits", use_container_width=True):
            try:
                modify_vip_limits(account_id, new_amt_limit, int(new_vol_limit))
                st.success(f"💾 Limits updated successfully for account **{account_id}**!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to update table record entries: {e}")


def _render_new_vip_registration(account_id: str) -> None:
    st.warning(f"Account ID **{account_id}** is not registered as a VIP Account.")

    # ── Blacklist warning banner ──────────────────────────────────────────
    account_is_blacklisted = is_blacklisted(account_id)
    if account_is_blacklisted:
        st.error(
            f"⚠️ Account **{account_id}** is on the **blacklist**. "
            "Whitelist it first before assigning VIP status."
        )
        if st.button("🔓 Whitelist Account", key="vip_tab_whitelist_btn", use_container_width=True):
            remove_from_blacklist(account_id)
            st.success(f"Account **{account_id}** has been whitelisted. You can now register it as VIP.")
            st.rerun()
        return  # Stop here — don't show the registration form

    st.markdown("Would you like to register this account as a new VIP entity?")

    with st.form("quick_vip_register"):
        q_amt = st.number_input("Initial Amount Limit", min_value=0.0, value=10000.0)
        q_vol = st.number_input("Initial Volume Limit", min_value=1, value=5)

        if st.form_submit_button("Provision New VIP Record"):
            if not is_valid_account(account_id):
                st.error("❌ Cannot provision VIP status: Account ID does not exist.")
                return
            try:
                provision_vip(account_id, q_amt, int(q_vol))
                st.success(f"Account **{account_id}** successfully created as a new VIP profile!")
                st.rerun()
            except VIPBlacklistedError as e:
                # Shouldn't normally reach here because we checked above,
                # but handled defensively.
                show_vip_blacklist_blocked_dialog(account_id)