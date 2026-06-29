import streamlit as st
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
from database.connection import get_pooled_connection, release_pooled_connection, get_db_connection

def get_user(username):
    conn = get_pooled_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    user_key,
                    username, 
                    password_plain AS password, 
                    custom_role_name,
                    has_access_transactions, 
                    has_access_vip_hub, 
                    has_access_chatbot
                FROM curated.users 
                WHERE username = %s AND is_active = TRUE;
            """, (username,))
            user = cur.fetchone()
        return user
    finally:
        release_pooled_connection(conn)

def create_user(username, password, role_name, access_trans, access_vip, access_bot):
    conn = get_pooled_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Check if the user already exists (active or inactive)
            cur.execute("SELECT is_active FROM curated.users WHERE username = %s;", (username,))
            existing = cur.fetchone()
            
            if existing:
                if existing['is_active']:
                    # User exists and is currently active
                    return "DUPLICATE"
                else:
                    # CRITICAL FIX: User exists but was soft-deleted. Reactivate and update them!
                    cur.execute("""
                        UPDATE curated.users 
                        SET password_plain = %s,
                            custom_role_name = %s,
                            has_access_transactions = %s,
                            has_access_vip_hub = %s,
                            has_access_chatbot = %s,
                            is_active = TRUE
                        WHERE username = %s;
                    """, (password, role_name, access_trans, access_vip, access_bot, username))
                    conn.commit()
                    return "SUCCESS"
            
            # 2. If user genuinely doesn't exist, insert a fresh record
            cur.execute("""
                INSERT INTO curated.users (
                    username, password_plain, custom_role_name, 
                    has_access_transactions, has_access_vip_hub, has_access_chatbot
                ) VALUES (%s, %s, %s, %s, %s, %s);
            """, (username, password, role_name, access_trans, access_vip, access_bot))
        
        conn.commit() 
        return "SUCCESS"
    except errors.UniqueViolation:
        conn.rollback()
        return "DUPLICATE"
    except Exception:
        conn.rollback()
        return "FAILED"
    finally:
        release_pooled_connection(conn)

def get_all_users():
    conn = get_pooled_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT username, custom_role_name, 
                       has_access_transactions, has_access_vip_hub, has_access_chatbot
                FROM curated.users 
                WHERE is_active = TRUE 
                ORDER BY username ASC;
            """)
            users = cur.fetchall()
        return users
    finally:
        release_pooled_connection(conn)

def update_user_permissions(username, role_name, access_trans, access_vip, access_bot):
    conn = get_pooled_connection()
    try:
        with conn.cursor() as cur:
            # Added `AND is_active = TRUE` to ensure we don't accidentally update a deactivated profile
            cur.execute("""
                UPDATE curated.users 
                SET custom_role_name = %s,
                    has_access_transactions = %s,
                    has_access_vip_hub = %s,
                    has_access_chatbot = %s
                WHERE username = %s AND is_active = TRUE;
            """, (role_name, access_trans, access_vip, access_bot, username))
        
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_pooled_connection(conn)

def delete_user(username):
    # Standardize to use ONLY the pooled connection method
    conn = get_pooled_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE curated.users SET is_active = FALSE WHERE username = %s;", 
                (username,)
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_pooled_connection(conn)