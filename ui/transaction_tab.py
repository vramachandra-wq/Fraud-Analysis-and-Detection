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
    # ── 1. INITIALIZE SESSION STATE KEYS (Prevents Silent UI Blanks) ───
    if "show_results" not in st.session_state:
        st.session_state.show_results = False
    if "device_cooldown_active" not in st.session_state:
        st.session_state.device_cooldown_active = False
    if "account_cooldown_active" not in st.session_state:
        st.session_state.account_cooldown_active = False
    if "geo_velocity_breach" not in st.session_state:
        st.session_state.geo_velocity_breach = False
    if "is_blacklisted" not in st.session_state:
        st.session_state.is_blacklisted = False
    if "vip_breach_type" not in st.session_state:
        st.session_state.vip_breach_type = None
    if "fraud_probability" not in st.session_state:
        st.session_state.fraud_probability = None

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

        # Reset any stale manual action steps from previous evaluations
        st.session_state.action_step = "idle"

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
        
        # ── Capture Advanced Velocity & Geo State flags ──────────────────────
        st.session_state.device_cooldown_active = result.get("device_cooldown_active", False)
        st.session_state.account_cooldown_active = result.get("account_cooldown_active", False)
        st.session_state.cooldown_remaining_hours = result.get("cooldown_remaining_hours", 4.0)
        st.session_state.geo_velocity_breach = result.get("geo_velocity_breach", False)
        st.session_state.geo_breach_details = result.get("geo_breach_details")
        
        # Explicitly declare UI status state for verification actions panel
        st.session_state.action_step = "idle"
        st.session_state.show_results = True
        st.rerun()

    # ── Results panel ────────────────────────────────────────────────────────
    if not st.session_state.get("show_results", False):
        return

    target_acct = st.session_state.saved_account_id
    cached_df = st.session_state.saved_input_df
    tx_details = cached_df.iloc[0].to_dict() if cached_df is not None else {}
    features_dict = st.session_state.features_dict

    if st.session_state.get("blacklist_msg"):
        st.info(st.session_state.blacklist_msg)

    # CONDITION 1 – Blacklisted account view
    if st.session_state.get("is_blacklisted", False):
        _render_blacklisted_view(target_acct, cached_df, tx_details, features_dict)

    # CONDITION 2 – Device Cooldown Rule View (More than 3 transactions/10 min block)
    elif st.session_state.get("device_cooldown_active", False):
        _render_device_cooldown_view(st.session_state.cooldown_remaining_hours)

    # CONDITION 3 – Global Account Transaction Volume Limit View
    elif st.session_state.get("account_cooldown_active", False):
        _render_account_cooldown_view(st.session_state.cooldown_remaining_hours)

    # CONDITION 4 – Geospatial Speed Rule View (>100 km within 1 hour)
    elif st.session_state.get("geo_velocity_breach", False):
        _render_geo_velocity_view(st.session_state.geo_breach_details)

    # CONDITION 5 – VIP breach view
    elif st.session_state.get("vip_breach_type"):
        _render_vip_breach_view(target_acct, tx_details)

    # CONDITION 6 – Standard ML result view
    else:
        _render_ml_result_view(target_acct, tx_details)


# ── Private sub-renderers ──────────────────────────────────────────────────

def _render_device_cooldown_view(remaining_hours: float) -> None:
    """Displays user warning layout for rapid frequency device velocity violations."""
    st.error("🚨 Device Limit Enforced")
    st.markdown(
        f"""
        <div style="
            background-color:#f8d7da;
            color:#721c24;
            padding:14px;
            border-radius:8px;
            font-weight:bold;
            text-align:left;
            font-size:16px;
            border: 1px solid #f5c6cb;
            margin-bottom:15px;">
            ⚠️ Suspicious Device Activity: This account has triggered more than 3 transactions from this specific device within a 10-minute window.
        </div>
        """,
        unsafe_allow_html=True
    )
    st.warning(f"⏳ Device locked. Please try again after **{remaining_hours:.1f} hours**.")
    st.metric(label="Fraud Probability Override", value="100.00%")


def _render_account_cooldown_view(remaining_hours: float) -> None:
    """Displays user warning layout for global rolling transaction volume limits."""
    st.error("🚨 Transaction Limit Reached")
    st.markdown(
        f"""
        <div style="
            background-color:#f8d7da;
            color:#721c24;
            padding:14px;
            border-radius:8px;
            font-weight:bold;
            text-align:left;
            font-size:16px;
            border: 1px solid #f5c6cb;
            margin-bottom:15px;">
            ⚠️ Transaction Limit Exceeded: This account has triggered more than 3 transactions across all platforms within a 10-minute window.
        </div>
        """,
        unsafe_allow_html=True
    )
    st.warning(f"⏳ Security Cooldown Active. Please try again later after **{remaining_hours:.1f} hours**.")
    st.metric(label="Fraud Probability Override", value="100.00%")


def _render_geo_velocity_view(breach_details: dict) -> None:
    """Displays layout warnings when impossible geographic distance criteria is met."""
    st.error("🚨 Impossible Travel Signature Flagged")
    st.markdown(
        """
        <div style="
            background-color:#f8d7da;
            color:#721c24;
            padding:14px;
            border-radius:8px;
            font-weight:bold;
            text-align:left;
            font-size:16px;
            border: 1px solid #f5c6cb;
            margin-bottom:15px;">
            🔴 Geospatial Velocity Exception: Distance covered exceeds allowed structural thresholds (>100 km covered within 1 hour).
        </div>
        """,
        unsafe_allow_html=True
    )
    
    if breach_details:
        st.info(
            f"**Calculated Velocity Distance:** {breach_details.get('distance_km'):.2f} km "
            f"| **Calculated Time Interval:** {breach_details.get('time_delta_mins')} mins"
        )
        st.text(f"Previous Log Location Reference ID: {breach_details.get('prev_loc_id')}")
        st.text(f"Current Evaluation Location Reference ID: {breach_details.get('curr_loc_id')}")
        
    st.metric(label="Fraud Probability Override", value="100.00%")


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
        st.warning("⚠️ Transaction amount exceeds configured VIP account limit.")
        st.info(f"**Configured Limit:** {tx_details.get('currency', '$')} {v_meta['limit_amt']:,} | **Attempted Amount:** {tx_details.get('currency', '$')} {tx_details.get('amount', 0.0):,}")
    
    elif breach == "VOLUME_REACHED":
        st.warning("⚠️ VIP account transaction volume limit has been reached.")
        st.info(f"**Volume Limit:** {v_meta['limit_vol']} | **Current Window Count:** {v_meta['current_vol']}")
        
    elif breach == "DEVICE_VELOCITY_BREACH":
        st.error("🚨 VIP Exception: High-frequency burst variant tracked on this device (>3 transactions in 10 mins).")
        st.info("💡 **Policy Check Required:** Review identity logs or request verbal confirmation before forcing an manual bypass.")
        
    elif breach == "GEOSPATIAL_VELOCITY_BREACH":
        st.error(f"🚨 VIP Exception: Impossible Travel Signature detected ({v_meta.get('geo_distance', 0.0):.2f} km covered within {v_meta.get('geo_time_delta', 0)} mins).")
        st.info("💡 **Policy Check Required:** High risk of account takeover. Confirm if customer is actively utilizing specialized remote access networks.")

    st.markdown("---")
    st.subheader("Verification Actions")

    current_step = st.session_state.get("action_step", "idle")

    if current_step == "idle":
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Approve Transaction", use_container_width=True):
                st.session_state.action_step = "pending_approve"
                st.rerun()
        with c2:
            if st.button("❌ Decline Transaction", use_container_width=True):
                st.session_state.action_step = "pending_reject"
                st.rerun()

    elif current_step == "pending_approve":
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
                    False, "VIP_MANUAL_APPROVE", f"Manually approved following a VIP {breach} override.",
                ))
                st.session_state.action_step = "idle"
                show_manual_approve_success_dialog()
        with c2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.action_step = "idle"
                st.rerun()

    elif current_step == "pending_reject":
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
                    False, "VIP_MANUAL_REJECT", f"Dropped via audit following a VIP {breach} rejection.",
                ))
                st.session_state.action_step = "idle"
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
    risk_cat = st.session_state.risk_cat

    if pred == 1:
        st.error("🚨 Fraudulent Transaction Detected")
    else:
        st.success("✅ Legitimate Behavioural")

    st.metric(label="Fraud Probability", value=f"{prob:.2%}")

    # Risk Category Display
    if risk_cat == "NO_RISK":
        st.markdown(
            """
            <div style="
                background-color:#d4edda;
                color:#155724;
                padding:12px;
                border-radius:8px;
                font-weight:bold;
                text-align:center;
                font-size:18px;">
                🟢 Risk Category: NO_RISK
            </div>
            """,
            unsafe_allow_html=True
        )

    elif risk_cat in ["LOW_RISK", "MEDIUM_RISK"]:
        st.markdown(
            f"""
            <div style="
                background-color:#fff3cd;
                color:#856404;
                padding:12px;
                border-radius:8px;
                font-weight:bold;
                text-align:center;
                font-size:18px;">
                🟡 Risk Category: {risk_cat}
            </div>
            """,
            unsafe_allow_html=True
        )

    elif risk_cat == "HIGH_RISK":
        st.markdown(
            """
            <div style="
                background-color:#f8d7da;
                color:#721c24;
                padding:12px;
                border-radius:8px;
                font-weight:bold;
                text-align:center;
                font-size:18px;">
                🔴 Risk Category: HIGH_RISK
            </div>
            """,
            unsafe_allow_html=True
        )

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
                st.session_state.display_vip_form = False
                show_vip_blacklist_blocked_dialog(target_acct)

    # After whitelisting inside the dialog, re-open VIP form automatically
    if st.session_state.pop("_pending_vip_after_whitelist", False):
        st.session_state.display_vip_form = True
        st.rerun()