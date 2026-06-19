import math
from datetime import datetime, timedelta
import pandas as pd
from database.account_repository import is_valid_account
from database.blacklist_repository import is_blacklisted
from database.vip_repository import get_vip_details, get_vip_volume_metrics
from database.transaction_repository import (
    log_transaction,
    get_recent_account_tx_count,
    get_last_transaction_location,
    get_location_coordinates,
    verify_device_exists,
    verify_location_exists,
    check_active_cooldown  # IMPORTED: Active database lookback verification method
)
from ml.prediction_service import run_ml_prediction, extract_engineered_features
from ai.summarizer import generate_transaction_summary


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance in kilometers between two coordinate sets."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def process_transaction(tx: dict) -> dict:
    """
    Full integrated fraud-detection pipeline for a single transaction.
    Enforces master validations, active historical cooldowns, blacklists, and velocity rules.
    """
    account_id = tx["account_id"]
    device_id = tx["device_id"]
    location_id = tx["location_id"]
    
    # ── STEP 0: MASTER DATA VALIDATION ──────────────────────────────────────
    if not is_valid_account(account_id):
        return {"validation_status": "INVALID_ACCOUNT"}
        
    if not verify_device_exists(device_id):
        return {"validation_status": "INVALID_DEVICE"}
        
    if not verify_location_exists(location_id):
        return {"validation_status": "INVALID_LOCATION"}

    current_tx_time = datetime.strptime(f"{tx['transaction_date']} {tx['transaction_time']}", "%Y-%m-%d %H:%M:%S")

    # Gather VIP status up front to evaluate conditional bypass rules
    vip_rules = get_vip_details(account_id)
    is_vip = vip_rules is not None

    # ── STEP 0.5: ACTIVE COOLDOWN ENFORCEMENT ────────────────────────────────
    # Enforces hard lock out if a non-VIP triggered a rapid rule limitation recently
    if not is_vip:
        active_lockout = check_active_cooldown(account_id, current_tx_time)
        if active_lockout:
            ai_summary = f"Blocked by active cooldown infrastructure safety layer. Lockout expires in {active_lockout['remaining_hours']:.2f} hours."
            return {
                "source": "RAPID_TRANSACTION_RULE",
                "account_cooldown_active": True,
                "cooldown_remaining_hours": active_lockout["remaining_hours"],
                "fraud_probability": 1.0,
                "prediction": 1,
                "risk_cat": "HIGH_RISK",
                "final_transaction_status": "FAILED",
                "ai_summary": ai_summary,
                "is_blacklisted": False,
                "validation_status": "VALID",
            }

    # Extract ML features up front
    input_df = pd.DataFrame([tx])
    features_dict = extract_engineered_features(input_df)

    # ── STEP 1: STATIC BLACKLIST CHECK ──────────────────────────────────────
    if is_blacklisted(account_id):
        ai_summary = generate_transaction_summary(tx, features_dict, 1.0, 1, "HIGH_RISK", "BLACKLIST_RULE")
        log_transaction((
            account_id, device_id, location_id, tx["transaction_type"],
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
            "validation_status": "VALID",
        }

    vip_details = None
    if is_vip:
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

    # ── STEP 2: FRAUD AND VELOCITY RULES RUNS ──────────────────────────────────
    
    # 2a. Rapid Transactions Rule (Rolling 2 minutes, max 3 tx. Block 4th) - BYPASSED FOR VIPs
    if not is_vip:
        two_mins_ago = current_tx_time - timedelta(minutes=2)
        recent_account_count = get_recent_account_tx_count(account_id, two_mins_ago)
        if recent_account_count >= 3:
            ai_summary = "Rapid transactions detected. Transaction limit reached. Try again after 2 hours."
            log_transaction((
                account_id, device_id, location_id, tx["transaction_type"],
                tx["channel"], tx["amount"], tx["currency"], "FAILED",
                tx["merchant_category"], str(tx["transaction_date"]),
                str(tx["transaction_time"]), tx["processing_time_ms"],
                1.0, 1, "HIGH_RISK", False, "RAPID_TRANSACTION_RULE", ai_summary,
            ))
            return {
                "source": "RAPID_TRANSACTION_RULE",
                "account_cooldown_active": True,
                "cooldown_remaining_hours": 2.0,
                "fraud_probability": 1.0,
                "prediction": 1,
                "risk_cat": "HIGH_RISK",
                "final_transaction_status": "FAILED",
                "ai_summary": ai_summary,
                "is_blacklisted": False,
                "features_dict": features_dict,
                "validation_status": "VALID",
            }

    # 2b. Device Switching Fraud Rule (Diff device within <= 5 mins) - BYPASSED FOR VIPs
    one_hour_ago = current_tx_time - timedelta(hours=1)
    last_tx = get_last_transaction_location(account_id, one_hour_ago)

    if not is_vip and last_tx:
        if last_tx.get("device_id") != device_id:
            time_delta_sec = (current_tx_time - last_tx["timestamp"]).total_seconds()
            if time_delta_sec <= 300.0:  # 5 minutes
                ai_summary = "Transaction blocked. Device switching detected."
                log_transaction((
                    account_id, device_id, location_id, tx["transaction_type"],
                    tx["channel"], tx["amount"], tx["currency"], "FAILED",
                    tx["merchant_category"], str(tx["transaction_date"]),
                    str(tx["transaction_time"]), tx["processing_time_ms"],
                    1.0, 1, "HIGH_RISK", False, "DEVICE_SWITCHING_RULE", ai_summary,
                ))
                return {
                    "source": "DEVICE_SWITCHING_RULE",
                    "device_switching_breach": True,
                    "fraud_probability": 1.0,
                    "prediction": 1,
                    "risk_cat": "HIGH_RISK",
                    "final_transaction_status": "FAILED",
                    "ai_summary": ai_summary,
                    "is_blacklisted": False,
                    "features_dict": features_dict,
                    "validation_status": "VALID",
                }

    # 2c. Geospatial Travel Limit Velocity Rule (>100 KM within <= 1 Hour) - ENFORCED FOR ALL (VIP + NON-VIP)
    if last_tx and last_tx["latitude"] is not None and last_tx["longitude"] is not None:
        curr_coords = get_location_coordinates(location_id)
        if curr_coords and curr_coords["latitude"] is not None and curr_coords["longitude"] is not None:
            distance = calculate_haversine_distance(
                last_tx["latitude"], last_tx["longitude"],
                curr_coords["latitude"], curr_coords["longitude"]
            )
            time_delta_mins = (current_tx_time - last_tx["timestamp"]).total_seconds() / 60.0
            
            if distance > 100.0 and time_delta_mins <= 60.0:
                if is_vip:
                    vip_details["distance_km"] = distance
                    vip_details["time_delta_mins"] = int(time_delta_mins)
                    return {
                        "source": "VIP_BREACH",
                        "is_blacklisted": False,
                        "vip_breach_type": "GEOSPATIAL_VELOCITY_BREACH",
                        "vip_details": vip_details,
                        "features_dict": features_dict,
                        "validation_status": "VALID",
                    }
                
                ai_summary = "Transaction blocked. Suspicious location velocity detected."
                log_transaction((
                    account_id, device_id, location_id, tx["transaction_type"],
                    tx["channel"], tx["amount"], tx["currency"], "FAILED",
                    tx["merchant_category"], str(tx["transaction_date"]),
                    str(tx["transaction_time"]), tx["processing_time_ms"],
                    1.0, 1, "HIGH_RISK", False, "GEOSPATIAL_VELOCITY_RULE", ai_summary,
                ))
                return {
                    "source": "GEOSPATIAL_VELOCITY_RULE",
                    "geo_velocity_breach": True,
                    "geo_breach_details": {
                        "distance_km": distance,
                        "time_delta_mins": int(time_delta_mins),
                        "prev_loc_id": last_tx["location_id"],
                        "curr_loc_id": location_id
                    },
                    "fraud_probability": 1.0,
                    "prediction": 1,
                    "risk_cat": "HIGH_RISK",
                    "final_transaction_status": "FAILED",
                    "ai_summary": ai_summary,
                    "is_blacklisted": False,
                    "features_dict": features_dict,
                    "validation_status": "VALID",
                }

    # ── STEP 3: CLEAN VIP PASSTHROUGH ───────────────────────────────────────
    if is_vip:
        ai_summary = generate_transaction_summary(tx, features_dict, 0.0, 0, "NO_RISK", "VIP_PASS", vip_context=vip_details)
        log_transaction((
            account_id, device_id, location_id, tx["transaction_type"],
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
            "validation_status": "VALID",
        }

    # ── STEP 4: STANDARD ML PATH (Standard Accounts Only) ───────────────────
    prob, pred, risk_cat = run_ml_prediction(input_df)
    final_status = "FAILED" if pred == 1 else tx.get("transaction_status", "PENDING")
    ai_summary = generate_transaction_summary(tx, features_dict, prob, pred, risk_cat, "ML_MODEL")
    
    log_transaction((
        account_id, device_id, location_id, tx["transaction_type"],
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
        "validation_status": "VALID",
    }