import streamlit as st
from groq import Groq
from config.settings import GROQ_API_KEY


@st.cache_resource
def get_groq_client() -> Groq | None:
    """Return a cached Groq client, or None if the API key is absent."""
    if not GROQ_API_KEY:
        return None
    return Groq(api_key=GROQ_API_KEY)