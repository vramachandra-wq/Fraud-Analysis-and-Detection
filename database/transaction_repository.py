import json
import streamlit as st
import pandas as pd
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
