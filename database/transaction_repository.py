import json
from datetime import datetime
import psycopg2
import pandas as pd
import streamlit as st
from database.connection import get_db_connection, get_pooled_connection, release_pooled_connection


def log_transaction(record_values: tuple) -> None:
    """Insert a transaction record into ml_predictions.transaction_logs."""
    insert_query = """
        INSERT INTO ml_predictions.transaction_logs (
            account_id, device_id, location_id, transaction_type, channel,
            amount, currency, transaction_status, merchant_category, transaction_date,
            transaction_time, processing_time_ms, fraud_probability, prediction, risk_category,
            blacklisted_account, fraud_source, ai_summary
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    try:
        with get_db_connection().cursor() as cursor:
            cursor.execute(insert_query, record_values)
        st.success("💾 Transaction Successfully Saved.")
    except Exception as e:
        st.error(f"❌ Database Logging Failed: {e}")


def log_chatbot_interaction(
    prompt: str,
    sql_code: str | None,
    df: pd.DataFrame | None,
    ai_summary: str,
) -> None:
    """Persist a chatbot query/response to curated.ai_chatbot_logs (silent on failure)."""
    conn = None
    try:
        conn = get_pooled_connection()
        cursor = conn.cursor()
        table_json = (
            json.dumps(df.head(100).to_dict(orient="records"))
            if df is not None and not df.empty
            else None
        )
        cursor.execute(
            """
            INSERT INTO curated.ai_chatbot_logs (prompt, sql_code, generated_table, ai_summary)
            VALUES (%s, %s, %s, %s);
            """,
            (prompt, sql_code, table_json, ai_summary),
        )
        conn.commit()
        cursor.close()
    except Exception as log_error:
        st.logger.get_logger(__name__).warning(f"[telemetry] DB log failed: {log_error}")
    finally:
        if conn:
            release_pooled_connection(conn)


def get_recent_device_tx_count(account_id: str, device_id: str, lookback_time: datetime) -> int:
    """
    Counts transactions for a given account and device within a rolling window 
    using the ml_predictions.transaction_logs table.
    """
    query = """
        SELECT COUNT(*) 
        FROM ml_predictions.transaction_logs
        WHERE account_id = %s 
          AND device_id = %s 
          AND (transaction_date || ' ' || transaction_time)::timestamp >= %s;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id, device_id, lookback_time))
            return cur.fetchone()[0]


def get_recent_account_tx_count(account_id: str, lookback_time: datetime) -> int:
    """
    Counts total global transactions for a standard account across ALL devices 
    within a rolling lookback window.
    """
    query = """
        SELECT COUNT(*) 
        FROM ml_predictions.transaction_logs
        WHERE account_id = %s 
          AND (transaction_date || ' ' || transaction_time)::timestamp >= %s;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (account_id, lookback_time))
            return cur.fetchone()[0]


def get_last_transaction_location(account_id: str, lookback_time: datetime) -> dict:
    """
    Retrieves the most recent transaction location context for an account,
    joining against curated.dim_location to extract spatial metrics.
    """
    query = """
        SELECT 
            t.location_id,
            (t.transaction_date || ' ' || t.transaction_time)::timestamp AS tx_timestamp,
            l.latitude,
            l.longitude
        FROM ml_predictions.transaction_logs t
        LEFT JOIN curated.dim_location l ON t.location_id = l.location_id
        WHERE t.account_id = %s
          AND (t.transaction_date || ' ' || t.transaction_time)::timestamp >= %s
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
                    "longitude": row[3]
                }
    return None


def get_location_coordinates(location_id: str) -> dict:
    """
    Fetches the spatial coordinates for the current target location.
    """
    query = "SELECT latitude, longitude FROM curated.dim_location WHERE location_id = %s;"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (location_id,))
            row = cur.fetchone()
            if row:
                return {"latitude": row[0], "longitude": row[1]}
    return None