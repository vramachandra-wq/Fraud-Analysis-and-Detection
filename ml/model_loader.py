import joblib
import streamlit as st
from config.settings import ML_MODEL_PATH


@st.cache_resource
def load_pipeline():
    """Load and cache the XGBoost fraud detection pipeline."""
    return joblib.load(ML_MODEL_PATH)
