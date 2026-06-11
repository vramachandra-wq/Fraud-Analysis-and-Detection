import psycopg2
import psycopg2.pool
import streamlit as st
from config.settings import DB_CONFIG, DB_CONFIG_CURATED


# ---------------------------------------------------------------------------
# Single persistent connection (used by fraud / VIP / blacklist operations)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db_connection() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn


# ---------------------------------------------------------------------------
# Threaded connection pool (used by the analytics chatbot)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_connection_pool() -> psycopg2.pool.ThreadedConnectionPool:
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1, maxconn=10, **DB_CONFIG_CURATED
    )


def get_pooled_connection() -> psycopg2.extensions.connection:
    return get_connection_pool().getconn()


def release_pooled_connection(conn: psycopg2.extensions.connection) -> None:
    get_connection_pool().putconn(conn)
