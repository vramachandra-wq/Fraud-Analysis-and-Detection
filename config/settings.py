import streamlit as st

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------
DB_CONFIG = dict(
    host="127.0.0.1",
    port=5434,
    dbname="fraud_olap",   
    user="postgres",             # Replace with your Credentials
    password="Master#123",       # Replace with your Credentials
)

# Same config with curated search_path for the chatbot
DB_CONFIG_CURATED = dict(
    **DB_CONFIG,
    options="-c search_path=curated,public",
)

# ---------------------------------------------------------------------------
# ML Model Path
# ---------------------------------------------------------------------------
ML_MODEL_PATH = r"ml\models\xgboost_fraud_detection_production.pkl"

# ---------------------------------------------------------------------------
# Groq / AI Configuration
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = st.secrets.get("GROQ_API_KEY", "") or ""
GROQ_SQL_MODEL = "llama-3.1-8b-instant"
GROQ_REPAIR_MODEL = "llama-3.3-70b-versatile"
GROQ_SUMMARY_MODEL = "llama-3.1-8b-instant"
