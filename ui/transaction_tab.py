import streamlit as st
import pandas as pd
from database.account_repository import is_valid_account
from database.blacklist_repository import add_to_blacklist
from database.transaction_repository import log_transaction
from ml.prediction_service import run_ml_prediction
from ai.summarizer import generate_transaction_summary
from services.fraud_service import process_transaction
from services.vip_service import provision_vip, VIPBlacklistedError
from ui.dialogs import (
    show_blacklist_dialog,
    show_whitelist_dialog,
    show_manual_approve_success_dialog,
    show_manual_reject_success_dialog,
    show_vip_blacklist_blocked_dialog,
)
from utils.constants import (
    TRANSACTION_TYPE_OPTIONS,
    CHANNEL_OPTIONS,
    CURRENCY_OPTIONS,
    TRANSACTION_STATUS_OPTIONS,
    MERCHANT_CATEGORY_OPTIONS,
)


def render_transaction_tab() -> None:
    st.header("Transaction Risk Evaluator")

    # ── Input form ───────────────────────────────────────────────────────────
    account_id = st.text_input("Account ID", key="pipeline_account_id")
    device_id = st.text_input("Device ID")
    location_id = st.text_input("Location ID")
    transaction_type = st.selectbox("Transaction Type", TRANSACTION_TYPE_OPTIONS)
    channel = st.selectbox("Channel", CHANNEL_OPTIONS)
    amount = st.number_input("Transaction Amount", min_value=0.0, value=1000.0)
    currency = st.selectbox("Currency", CURRENCY_OPTIONS)
    transaction_status = st.selectbox("Transaction Status", TRANSACTION_STATUS_OPTIONS)
    merchant_category = st.selectbox("Merchant Category", MERCHANT_CATEGORY_OPTIONS)
    transaction_date = st.date_input("Transaction Date")
    transaction_time = st.time_input("Transaction Time")
    processing_time_ms = st.number_input("Processing Time (ms)", min_value=0, value=500)

    if st.button("Detect Fraud Risk", use_container_width=True):
        if not account_id.strip() or not device_id.strip() or not location_id.strip():
            st.warning("⚠️ Please Enter Valid Values.")
            st.stop()

        if not is_valid_account(account_id):
            st.error("❌ Invalid account. Transaction cannot be processed.")
            st.stop()

        tx = {
            "account_id": account_id,
            "device_id": device_id,
            "location_id": location_id,
            "transaction_type": transaction_type,
            "channel": channel,
            "amount": amount,
            "currency": currency,
            "transaction_status": transaction_status,
            "merchant_category": merchant_category,
            "transaction_date": str(transaction_date),
            "transaction_time": str(transaction_time),
            "processing_time_ms": processing_time_ms,
        }

        result = process_transaction(tx)

        st.session_state.saved_account_id = account_id
        st.session_state.saved_input_df = pd.DataFrame([tx])
        st.session_state.blacklist_msg = None
        st.session_state.is_blacklisted = result.get("is_blacklisted", False)
        st.session_state.fraud_probability = result.get("fraud_probability")
        st.session_state.prediction = result.get("prediction")
        st.session_state.risk_cat = result.get("risk_cat")
        st.session_state.final_transaction_status = result.get("final_transaction_status")
        st.session_state.ai_summary = result.get("ai_summary")
        st.session_state.features_dict = result.get("features_dict")
        st.session_state.vip_breach_type = result.get("vip_breach_type")
        st.session_state.vip_details = result.get("vip_details")
        st.session_state.show_results = True
        st.rerun()

    # ── Results panel ────────────────────────────────────────────────────────
    if not st.session_state.show_results:
        return

    target_acct = st.session_state.saved_account_id
    cached_df = st.session_state.saved_input_df
    tx_details = cached_df.iloc[0].to_dict() if cached_df is not None else {}
    features_dict = st.session_state.features_dict

    if st.session_state.blacklist_msg:
        st.info(st.session_state.blacklist_msg)

    # CONDITION 1 – Blacklisted account view
    if st.session_state.is_blacklisted:
        _render_blacklisted_view(target_acct, cached_df, tx_details, features_dict)

    # CONDITION 2 – VIP breach view
    elif st.session_state.vip_breach_type:
        _render_vip_breach_view(target_acct, tx_details)

    # CONDITION 3 – Standard ML result view
    else:
        _render_ml_result_view(target_acct, tx_details)


# ── Private sub-renderers ──────────────────────────────────────────────────

def _render_blacklisted_view(
    target_acct: str,
    cached_df: pd.DataFrame,
    tx_details: dict,
    features_dict: dict,
) -> None:
    st.error("🚨 Account Blocked")
    st.metric(label="Fraud Probability", value="100.00%")

    if st.button("🔓 Whitelist Account", use_container_width=True):
        from database.blacklist_repository import remove_from_blacklist
        remove_from_blacklist(target_acct)

        prob, pred, risk_cat = run_ml_prediction(cached_df)
        final_status = "FAILED" if pred == 1 else tx_details.get("transaction_status", "PENDING")

        st.session_state.is_blacklisted = False
        st.session_state.fraud_probability = prob
        st.session_state.prediction = pred
        st.session_state.risk_cat = risk_cat
        st.session_state.final_transaction_status = final_status
        st.session_state.ai_summary = generate_transaction_summary(
            tx_details, features_dict, prob, pred, risk_cat, "ML_MODEL"
        )

        log_transaction((
            target_acct, tx_details["device_id"], tx_details["location_id"],
            tx_details["transaction_type"], tx_details["channel"], tx_details["amount"],
            tx_details["currency"], final_status, tx_details["merchant_category"],
            str(tx_details["transaction_date"]), str(tx_details["transaction_time"]),
            int(tx_details["processing_time_ms"]), prob, pred, risk_cat,
            False, "ML_MODEL", st.session_state.ai_summary,
        ))
        show_whitelist_dialog(target_acct)


def _render_vip_breach_view(target_acct: str, tx_details: dict) -> None:
    v_meta = st.session_state.vip_details
    breach = st.session_state.vip_breach_type

    if breach == "AMOUNT_EXCEEDED":
        st.warning(
            "⚠️ Transaction amount exceeds configured VIP account limit. "
            "Confirm the legitimacy of the transaction with the account holder."
        )
        st.info(
            f"**Configured Limit:** {tx_details.get('currency', '$')} {v_meta['limit_amt']:,} "
            f"| **Attempted Amount:** {tx_details.get('currency', '$')} {tx_details.get('amount', 0.0):,}"
        )
    else:
        st.warning(
            "⚠️ VIP account transaction volume limit has been reached. "
            "Confirm the legitimacy of the transaction with the account holder."
        )
        st.info(
            f"**Volume Limit:** {v_meta['limit_vol']} "
            f"| **Current Window Count:** {v_meta['current_vol']}"
        )

    st.markdown("---")
    st.subheader("Verification Actions")

    if st.session_state.get("action_step", "idle") == "idle":
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Approve Transaction", use_container_width=True):
                st.session_state.action_step = "pending_approve"
                st.rerun()
        with c2:
            if st.button("❌ Decline Transaction", use_container_width=True):
                st.session_state.action_step = "pending_reject"
                st.rerun()

    elif st.session_state.action_step == "pending_approve":
        st.warning("⚠️ **Confirm Force Manual Approval:** Are you sure you want to bypass active VIP restrictions?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Yes", type="primary", use_container_width=True):
                log_transaction((
                    target_acct, tx_details["device_id"], tx_details["location_id"],
                    tx_details["transaction_type"], tx_details["channel"], tx_details["amount"],
                    tx_details["currency"], "COMPLETED", tx_details["merchant_category"],
                    str(tx_details["transaction_date"]), str(tx_details["transaction_time"]),
                    int(tx_details["processing_time_ms"]), 0.01, 0, "NO_RISK",
                    False, "VIP_MANUAL_APPROVE", "Manually approved.",
                ))
                show_manual_approve_success_dialog()
        with c2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.action_step = "idle"
                st.rerun()

    elif st.session_state.action_step == "pending_reject":
        st.error("⚠️ **Confirm Drop Transaction:** Are you sure you want to decline this transaction?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Yes", type="primary", use_container_width=True):
                log_transaction((
                    target_acct, tx_details["device_id"], tx_details["location_id"],
                    tx_details["transaction_type"], tx_details["channel"], tx_details["amount"],
                    tx_details["currency"], "FAILED", tx_details["merchant_category"],
                    str(tx_details["transaction_date"]), str(tx_details["transaction_time"]),
                    int(tx_details["processing_time_ms"]), 0.95, 1, "HIGH_RISK",
                    False, "VIP_MANUAL_REJECT", "Dropped via audit.",
                ))
                show_manual_reject_success_dialog()
        with c2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.action_step = "idle"
                st.rerun()


def _render_ml_result_view(target_acct: str, tx_details: dict) -> None:
    if st.session_state.fraud_probability is None:
        st.session_state.show_results = False
        st.rerun()
        return

    st.subheader("Evaluation")
    prob = st.session_state.fraud_probability
    pred = st.session_state.prediction

    if pred == 1:
        st.error("🚨 Fraudulent Transaction Detected")
    else:
        st.success("✅ Legitimate Behavioural")

    st.metric(label="Fraud Probability", value=f"{prob:.2%}")

    if st.session_state.ai_summary:
        st.markdown("### AI Summary")
        st.info(st.session_state.ai_summary)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚫 Blacklist Account", use_container_width=True):
            add_to_blacklist(target_acct)
            show_blacklist_dialog(target_acct)
    with col2:
        if st.button("👑 Add Account to VIP Tier", use_container_width=True):
            st.session_state.display_vip_form = True

    if st.session_state.get("display_vip_form", False):
        _render_inline_vip_form(target_acct)


def _render_inline_vip_form(target_acct: str) -> None:
    """Inline VIP provisioning form with blacklist guard."""
    with st.form("vip_creation_form"):
        lim_amt = st.number_input("Transaction Amount Limit", min_value=100.0, value=50000.0)
        lim_vol = st.number_input("Transaction Volume Limit", min_value=1, value=10)
        if st.form_submit_button("Commit VIP Record"):
            try:
                provision_vip(target_acct, lim_amt, int(lim_vol))
                st.success(f"Account {target_acct} added to VIP schema.")
                st.session_state.display_vip_form = False
                st.rerun()
            except VIPBlacklistedError:
                # Dismiss form, then open the specialised dialog
                st.session_state.display_vip_form = False
                show_vip_blacklist_blocked_dialog(target_acct)

    # After whitelisting inside the dialog, re-open VIP form automatically
    if st.session_state.pop("_pending_vip_after_whitelist", False):
        st.session_state.display_vip_form = True
        st.rerun()
