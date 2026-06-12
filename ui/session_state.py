import streamlit as st

# All session-state keys used by the fraud detection tab
_FRAUD_STATES = [
    "show_results",
    "blacklist_msg",
    "saved_input_df",
    "ai_summary",
    "trigger_blacklist_popup",
    "trigger_whitelist_popup",
    "vip_breach_type",
    "vip_details",
    "features_dict",
    "is_blacklisted",
    "fraud_probability",
    "prediction",
    "risk_cat",
    "final_transaction_status",
    "saved_account_id",
    "action_step",
    "display_vip_form",
]

_BOOL_STATES = {
    "show_results",
    "trigger_blacklist_popup",
    "trigger_whitelist_popup",
    "is_blacklisted",
    "authenticated",  # Added authenticated to the boolean tracking set
}


def init_session_state() -> None:
    """Initialise all required session-state keys if not already present."""
    for key in _FRAUD_STATES:
        if key not in st.session_state:
            st.session_state[key] = False if key in _BOOL_STATES else None

    # Global Chatbot State
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # State Overrides / Safeguards
    if "action_step" not in st.session_state:
        st.session_state["action_step"] = "idle"

    if "display_vip_form" not in st.session_state:
        st.session_state["display_vip_form"] = False

    # ── Admin Auth Initialization ──────────────────────────────────────────
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False


def reset_fraud_results() -> None:
    """Clear result-related state so the form returns to its blank state."""
    keys_to_clear = [
        "show_results", "blacklist_msg", "saved_input_df", "ai_summary",
        "vip_breach_type", "vip_details", "features_dict", "is_blacklisted",
        "fraud_probability", "prediction", "risk_cat", "final_transaction_status",
        "saved_account_id", "action_step",
    ]
    for key in keys_to_clear:
        st.session_state[key] = False if key in _BOOL_STATES else None
    st.session_state["action_step"] = "idle"