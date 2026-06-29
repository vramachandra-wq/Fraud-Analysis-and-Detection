import json
from datetime import datetime
import psycopg2
import pandas as pd
import streamlit as st
from database.connection import get_db_connection, get_pooled_connection, release_pooled_connection


def log_transaction(record_values: tuple) -> None:
    """Insert a transaction record into ml_predictions.transaction_logs with connection safety."""
    insert_query = """
        INSERT INTO ml_predictions.transaction_logs (
            account_id, device_id, location_id, transaction_type, channel,
            amount, currency, transaction_status, merchant_category, transaction_date,
            transaction_time, processing_time_ms, fraud_probability, prediction, risk_category,
            blacklisted_account, fraud_source, ai_summary
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(insert_query, record_values)
        conn.commit()
        st.success("💾 Transaction Successfully Saved.")
    except Exception as e:
        if hasattr(conn, "rollback"):
            conn.rollback()
        st.error(f"❌ Database Logging Failed: {e}")

def log_chatbot_interaction(
    user_query: str, 
    sql_query: str | None, 
    result_df: pd.DataFrame | None, 
    assistant_summary: str,
    user_key: int | None = None,
    username: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0       
) -> None:
    """
    Logs chatbot interactions into curated.ai_chatbot_logs for monitoring.
    """
    # Convert DataFrame to a JSON string if data exists
    generated_table_json = None
    if result_df is not None and not result_df.empty:
        generated_table_json = json.dumps(result_df.to_dict(orient="records"))

    # Updated query to include token metrics columns
    query = """
        INSERT INTO curated.ai_chatbot_logs (
            prompt, sql_code, generated_table, ai_summary, user_key, username, 
            prompt_tokens, completion_tokens, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
    """

    conn = get_pooled_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                query, 
                (
                    user_query, 
                    sql_query, 
                    generated_table_json, 
                    assistant_summary, 
                    user_key, 
                    username,
                    prompt_tokens,     
                    completion_tokens
                )
            )
        conn.commit()
    except psycopg2.Error as e:
        if hasattr(conn, "rollback"):
            conn.rollback()
        # Log via print or internal python logging so it does not break UI stream UX
        print(f"Database logging failed: {e}") 
    finally:
        release_pooled_connection(conn)

def get_recent_device_tx_count(account_id: str, device_id: str, lookback_time: datetime) -> int:
    """Counts transactions for a given account and device within a rolling window."""
    # FIX: Avoided string concatenation type conversions for performance and query safety
    query = """
        SELECT COUNT(*) 
        FROM ml_predictions.transaction_logs
        WHERE account_id = %s 
          AND device_id = %s 
          AND (EXTRACT(YEAR FROM transaction_date)::int = EXTRACT(YEAR FROM %s::timestamp)::int) -- Contextual performance optimization
          AND (transaction_date + transaction_time) >= %s;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id, device_id, lookback_time, lookback_time))
            return cur.fetchone()[0]


def get_recent_account_tx_count(account_id: str, lookback_time: datetime) -> int:
    """Counts total global transactions for a standard account across ALL devices."""
    query = """
        SELECT COUNT(*) 
        FROM ml_predictions.transaction_logs
        WHERE account_id = %s 
          AND (transaction_date + transaction_time) >= %s;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id, lookback_time))
            return cur.fetchone()[0]


def get_last_transaction_location(account_id: str, lookback_time: datetime) -> dict:
    """Retrieves the most recent transaction context for an account joining spatial metrics."""
    query = """
        SELECT 
            t.location_id,
            (t.transaction_date + t.transaction_time) AS tx_timestamp,
            l.latitude,
            l.longitude,
            t.device_id
        FROM ml_predictions.transaction_logs t
        LEFT JOIN curated.dim_location l ON t.location_id = l.location_id
        WHERE t.account_id = %s
          AND (t.transaction_date + t.transaction_time) >= %s
        ORDER BY tx_timestamp DESC
        LIMIT 1;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id, lookback_time))
            row = cur.fetchone()
            if row:
                return {
                    "location_id": row[0],
                    "timestamp": row[1],
                    "latitude": row[2],
                    "longitude": row[3],
                    "device_id": row[4]
                }
    return None


def get_location_coordinates(location_id: str) -> dict:
    """
    Fetches the spatial coordinates for the current target location from master schema.
    """
    query = "SELECT latitude, longitude FROM curated.dim_location WHERE location_id = %s;"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (location_id,))
            row = cur.fetchone()
            if row:
                return {"latitude": row[0], "longitude": row[1]}
    return None


def verify_device_exists(device_id: str) -> bool:
    """Validates if a device entry exists inside master data schema table."""
    if not device_id or not device_id.strip():
        return False
    query = "SELECT 1 FROM curated.dim_device WHERE device_id = %s LIMIT 1;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (device_id.strip(),))
                return cur.fetchone() is not None
    except Exception:
        return False


def verify_location_exists(location_id: str) -> bool:
    """Validates if a location entry exists inside data schema table."""
    if not location_id or not location_id.strip():
        return False
    query = "SELECT 1 FROM curated.dim_location WHERE location_id = %s LIMIT 1;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (location_id.strip(),))
                return cur.fetchone() is not None
    except Exception:
        return False


def check_active_cooldown(account_id: str, current_time: datetime) -> dict | None:
    """Looks back into the logs to find if the user triggered a rapid transaction limit breach."""
    query = """
        SELECT (transaction_date + transaction_time) AS breach_time
        FROM ml_predictions.transaction_logs
        WHERE account_id = %s 
          AND fraud_source = 'RAPID_TRANSACTION_RULE'
          AND transaction_status = 'FAILED'
        ORDER BY breach_time DESC
        LIMIT 1;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (account_id,))
                row = cur.fetchone()
                if row:
                    last_breach = row[0]
                    elapsed_seconds = (current_time - last_breach).total_seconds()
                    if elapsed_seconds < 7200:
                        remaining_hours = (7200 - elapsed_seconds) / 3600.0
                        return {"remaining_hours": remaining_hours}
    except Exception:
        return None
    return None