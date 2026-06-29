import streamlit as st
import certifi
import httpx
from groq import Groq
from config.settings import GROQ_API_KEY

def get_groq_client() -> Groq | None:

    if not GROQ_API_KEY:
        return None

    return Groq(
        api_key=GROQ_API_KEY,
        http_client=httpx.Client(
            verify=False
        )
    )