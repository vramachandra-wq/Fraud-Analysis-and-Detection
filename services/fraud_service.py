import pandas as pd
from database.account_repository import is_valid_account
from database.blacklist_repository import is_blacklisted
from database.vip_repository import get_vip_details, get_vip_volume_metrics
from database.transaction_repository import log_transaction
from ml.prediction_service import run_ml_prediction, extract_engineered_features
from ai.summarizer import generate_transaction_summary


def process_transaction(tx: dict) -> dict:
    """
    Full fraud-detection pipeline for a single transaction.

    Returns a result dict with keys:
        source, fraud_probability, prediction, risk_cat,
        final_transaction_status, ai_summary, is_blacklisted,
        vip_breach_type (optional), vip_details (optional)
    """
    account_id = tx["account_id"]

    input_df = pd.DataFrame([tx])
    features_dict = extract_engineered_features(input_df)

    # ── Blacklist check ──────────────────────────────────────────────────────
    if is_blacklisted(account_id):
        ai_summary = generate_transaction_summary(
            tx, features_dict, 1.0, 1, "HIGH_RISK", "BLACKLIST_RULE"
        )
        log_transaction((
            account_id, tx["device_id"], tx["location_id"], tx["transaction_type"],
            tx["channel"], tx["amount"], tx["currency"], "FAILED",
            tx["merchant_category"], str(tx["transaction_date"]),
            str(tx["transaction_time"]), tx["processing_time_ms"],
            1.0, 1, "HIGH_RISK", True, "BLACKLIST_RULE", ai_summary,
        ))
        return {
            "source": "BLACKLIST_RULE",
            "fraud_probability": 1.0,
            "prediction": 1,
            "risk_cat": "HIGH_RISK",
            "final_transaction_status": "FAILED",
            "ai_summary": ai_summary,
            "is_blacklisted": True,
            "features_dict": features_dict,
        }

    # ── VIP check ────────────────────────────────────────────────────────────
    vip_rules = get_vip_details(account_id)
    if vip_rules:
        amt_limit = float(vip_rules["amount_per_transaction_limit"])
        vol_limit = int(vip_rules["transactions_limit"])
        current_vol, last_ts = get_vip_volume_metrics(account_id)
        remaining_vol = max(0, vol_limit - (current_vol + 1))

        vip_details = {
            "limit_amt": amt_limit,
            "limit_vol": vol_limit,
            "current_vol": current_vol + 1,
            "remaining_vol": remaining_vol,
            "last_ts": str(last_ts),
        }

        if tx["amount"] > amt_limit:
            return {
                "source": "VIP_BREACH",
                "is_blacklisted": False,
                "vip_breach_type": "AMOUNT_EXCEEDED",
                "vip_details": vip_details,
                "features_dict": features_dict,
            }

        if current_vol >= vol_limit:
            return {
                "source": "VIP_BREACH",
                "is_blacklisted": False,
                "vip_breach_type": "VOLUME_REACHED",
                "vip_details": vip_details,
                "features_dict": features_dict,
            }

        # VIP pass — auto-approve
        ai_summary = generate_transaction_summary(
            tx, features_dict, 0.0, 0, "NO_RISK", "VIP_PASS",
            vip_context=vip_details,
        )
        log_transaction((
            account_id, tx["device_id"], tx["location_id"], tx["transaction_type"],
            tx["channel"], tx["amount"], tx["currency"], "COMPLETED",
            tx["merchant_category"], str(tx["transaction_date"]),
            str(tx["transaction_time"]), tx["processing_time_ms"],
            0.0, 0, "NO_RISK", False, "VIP_PASS", ai_summary,
        ))
        return {
            "source": "VIP_PASS",
            "fraud_probability": 0.0,
            "prediction": 0,
            "risk_cat": "NO_RISK",
            "final_transaction_status": "COMPLETED",
            "ai_summary": ai_summary,
            "is_blacklisted": False,
            "vip_details": vip_details,
            "features_dict": features_dict,
        }

    # ── Standard ML path ─────────────────────────────────────────────────────
    prob, pred, risk_cat = run_ml_prediction(input_df)
    final_status = "FAILED" if pred == 1 else tx.get("transaction_status", "PENDING")
    ai_summary = generate_transaction_summary(
        tx, features_dict, prob, pred, risk_cat, "ML_MODEL"
    )
    log_transaction((
        account_id, tx["device_id"], tx["location_id"], tx["transaction_type"],
        tx["channel"], tx["amount"], tx["currency"], final_status,
        tx["merchant_category"], str(tx["transaction_date"]),
        str(tx["transaction_time"]), tx["processing_time_ms"],
        prob, pred, risk_cat, False, "ML_MODEL", ai_summary,
    ))
    return {
        "source": "ML_MODEL",
        "fraud_probability": prob,
        "prediction": pred,
        "risk_cat": risk_cat,
        "final_transaction_status": final_status,
        "ai_summary": ai_summary,
        "is_blacklisted": False,
        "features_dict": features_dict,
    }