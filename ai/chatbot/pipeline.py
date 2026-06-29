from __future__ import annotations
import json
import re
import pandas as pd
import psycopg2
import streamlit as st
from ai.groq_client import get_groq_client
from config.settings import GROQ_REPAIR_MODEL, GROQ_SQL_MODEL, GROQ_SUMMARY_MODEL
from database.connection import get_pooled_connection, release_pooled_connection
from database.transaction_repository import log_chatbot_interaction
from .components import render_assistant_turn
from .config import BLOCKED_KEYWORDS, KNOWN_DIMENSION_TABLES, SQL_SYSTEM_PROMPT, VISUALIZATION_SYSTEM_PROMPT

# ── Persistent Multi-User Chat History Layer (Strict Identity Isolation) ───

def save_message_to_db(user_key: int, role: str, message_payload: str | dict) -> None:
    """
    Persists a chat event into the PostgreSQL ledger for long-term multi-user memory.
    """
    if not user_key:
        return
    conn = get_pooled_connection()
    try:
        with conn.cursor() as cursor:
            payload_str = json.dumps(message_payload) if isinstance(message_payload, dict) else message_payload
            cursor.execute(
                "INSERT INTO curated.chatbot_history (user_key, role, message_json) VALUES (%s, %s, %s);",
                (int(user_key), str(role), payload_str)
            )
        conn.commit()
    except Exception as e:
        print(f"Failed to persist chat record to core database: {e}")
    finally:
        release_pooled_connection(conn)


def load_user_chat_history(user_key: int) -> list[dict]:
    """
    Retrieves the chronological history exclusively matching the active user_key.
    Guarantees strict data isolation across user sessions.
    """
    if not user_key:
        return []
    conn = get_pooled_connection()
    messages = []
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT role, message_json FROM curated.chatbot_history WHERE user_key = %s ORDER BY created_at ASC;",
                (int(user_key),)
            )
            for row in cursor.fetchall():
                role, payload = row[0], row[1]
                if role == "assistant":
                    try:
                        messages.append(json.loads(payload))
                    except json.JSONDecodeError:
                        messages.append({"role": "assistant", "content": payload, "is_followup": True})
                else:
                    messages.append({"role": "user", "content": payload})
    except Exception as e:
        print(f"Error hydrating user session space: {e}")
    finally:
        release_pooled_connection(conn)
    return messages


# ── SQL extraction / validation / repair ───────────────────────────────────

def _extract_sql(text: str) -> str:
    match = re.search(r"```sql\s+(.*?)\s+```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def _validate_sql(sql: str) -> tuple[bool, str]:
    sql_clean = sql.strip()

    # Remove comments
    sql_clean = re.sub(r"--.*?\n", "\n", sql_clean)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)

    # Remove string literals
    sql_clean = re.sub(r"'.*?'", "''", sql_clean)
    sql_clean = re.sub(r'".*?"', '""', sql_clean)  # FIX 1: removed stray `woods=r` prefix

    sql_lower = " ".join(sql_clean.lower().split())

    # Only SELECT or CTE queries allowed
    if not (sql_lower.startswith("select") or sql_lower.startswith("with")):
        return False, "Only read-only SELECT or WITH (CTE) queries are permitted."

    # Block DML/DDL statements
    for kw in BLOCKED_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_lower):
            return False, f"Blocked keyword detected: `{kw.upper()}`. Only SELECT/WITH queries are allowed."

    # Prevent duplicate dimension joins
    join_pattern = re.compile(r"(?:from|join)\s+(?:curated\.)?(\w+)", re.IGNORECASE)
    table_counts: dict[str, int] = {}
    for tbl in join_pattern.findall(sql_lower):
        table_counts[tbl] = table_counts.get(tbl, 0) + 1

    for dim in KNOWN_DIMENSION_TABLES:
        count = table_counts.get(dim, 0)
        if count > 1:
            return False, f"The generated SQL joins `{dim}` {count} times. Each dimension table may only appear once."

    # Validate date functions (Adding dc.date_of_birth here for age bin derivations)
    date_functions = ["extract", "date_trunc", "age"]
    allowed_date_columns = ["ft.transaction_date", "ft.transaction_time", "dc.date_of_birth"]

    for func in date_functions:
        matches = re.findall(rf"{func}\s*\([\s\S]*?\)", sql_lower, re.IGNORECASE)
        for match in matches:
            if not any(col.lower() in match.lower() for col in allowed_date_columns):
                return False, f"Invalid use of {func.upper()} on a non-date column: {match}"

    return True, ""


def _repair_sql(sql: str, validation_error: str) -> str:
    client = get_groq_client()
    if not client:
        return sql

    repair_prompt = f"""You are an expert PostgreSQL SQL engineer.
The following SQL either violated validation rules or failed during database execution.
Fix the SQL so it executes successfully. Make the minimum required changes.
Do not rewrite the query unless absolutely necessary.

ERROR:
{validation_error}

DATABASE RULES:
- Only SELECT statements are allowed.
- The fact table (fact_transactions) must be the driving table.
- Dimension tables may appear at most once.
- Never self-join a dimension table.
- Join dimensions directly to fact_transactions.
- Use business keys, never surrogate keys.

SCD TYPE 2 RULES:
- Always filter dimensions with is_current = true unless explicitly requested otherwise.

DATE FUNCTION RULES:
- EXTRACT(), DATE_TRUNC(), and AGE() may only be used on:
    ft.transaction_date
    ft.transaction_time
    dc.date_of_birth
- Never apply date functions to numeric columns.

POSTGRES RULES:
- Every non-aggregated column in SELECT must appear in GROUP BY.
- Preserve all filters, aggregations, business logic, and aliases.
- Use table aliases everywhere.

OUTPUT RULES:
- Return ONLY one executable PostgreSQL SELECT statement.
- Wrap it in a ```sql code block.
- Do not include any explanation or commentary.

ORIGINAL SQL:
```sql
{sql}
```"""  # FIX 2: added closing ``` fence for the ORIGINAL SQL block

    try:  # FIX 3: corrected indentation — try/except was outside the function body
        response = client.chat.completions.create(
            model=GROQ_REPAIR_MODEL,
            messages=[{"role": "user", "content": repair_prompt}],
            temperature=0,
            max_tokens=800,
        )
        repaired_sql = _extract_sql(response.choices[0].message.content)
        return repaired_sql or sql
    except Exception:
        return sql


# ── Intent classification ──────────────────────────────────────────────────

def _is_sql_generation_needed(user_query: str, last_assistant_msg: dict | None) -> bool:
    if not last_assistant_msg or last_assistant_msg.get("df") is None:
        return True

    client = get_groq_client()
    if not client:
        return True

    intent_prompt = (
        "You are an AI assistant helping a data pipeline determine route logic.\n"
        "Analyze the user's latest message and decide if they are asking for NEW data "
        "that requires writing a database query, or if they are asking a follow-up question "
        "discussing, explaining, filtering, or summarizing the data already shown to them.\n\n"
        f"User Message: \"{user_query}\"\n\n"
        "Respond with EXACTLY one word: 'NEW' or 'DISCUSSION'. Do not include punctuation."
    )

    try:
        response = client.chat.completions.create(
            model=GROQ_REPAIR_MODEL,
            messages=[{"role": "user", "content": intent_prompt}],
            temperature=0,
            max_tokens=5,
        )
        intent = response.choices[0].message.content.strip().upper()
        return "NEW" in intent
    except Exception:
        return True


# ── Core pipeline ──────────────────────────────────────────────────────────

def run_query_pipeline(user_query: str, container) -> None:
    """
    Execute the full analytics pipeline for a single user question.
    """
    current_username = st.session_state.get("username")
    current_user_key = st.session_state.get("user_key")

    # 🔐 Fallback Identity Resolution Map
    if current_user_key is None and current_username is not None:
        conn = get_pooled_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT user_key FROM curated.users WHERE username = %s LIMIT 1;",
                    (current_username,)
                )
                row = cursor.fetchone()
                if row:
                    current_user_key = row[0]
                    st.session_state["user_key"] = current_user_key
        except Exception as lookup_err:
            print(f"Failed identity lookup for user '{current_username}': {lookup_err}")
        finally:
            release_pooled_connection(conn)

    client = get_groq_client()
    if not client:
        with container:
            st.error("🔑 Groq API key missing — add GROQ_API_KEY to .streamlit/secrets.toml.")
        return

    # 📥 Save incoming query block immediately to the isolated message ledger
    save_message_to_db(current_user_key, "user", user_query)

    llm_payload = [{"role": "system", "content": SQL_SYSTEM_PROMPT}]
    for msg in st.session_state.get("messages", []):
        if msg.get("role") in ("user", "assistant"):
            content = msg.get("content", "")
            if msg.get("role") == "assistant" and msg.get("sql"):
                content += f"\n\nHistorical SQL generated for this turn:\n```sql\n{msg['sql']}\n```"
            llm_payload.append({"role": msg["role"], "content": content})

    total_prompt_tokens = 0
    total_completion_tokens = 0

    with container:
        with st.chat_message("assistant"):
            with st.status("Processing Analytics Request…", expanded=True) as status:
                sql_query: str | None = None
                result_df: pd.DataFrame | None = None
                generate_new_sql = True

                try:
                    history = st.session_state.get("messages", [])
                    last_assistant = next(
                        (m for m in reversed(history) if m["role"] == "assistant"), None
                    )

                    generate_new_sql = _is_sql_generation_needed(user_query, last_assistant)

                    if generate_new_sql:
                        # ── BRANCH A: GENERATE NEW SQL ──────────────────────
                        status.write("🧠 Generating SQL query…")
                        completion = client.chat.completions.create(
                            model=GROQ_SQL_MODEL,
                            messages=llm_payload,
                            temperature=0.0,
                            max_tokens=600,
                        )
                        raw_sql_response = completion.choices[0].message.content.strip()

                        if hasattr(completion, "usage") and completion.usage:
                            total_prompt_tokens += completion.usage.prompt_tokens
                            total_completion_tokens += completion.usage.completion_tokens

                        # 🛑 GUARDRAIL CHECK: DATA UNAVAILABLE / WRONG COLUMNS DECLINE
                        if "ERROR: DATA_NOT_AVAILABLE" in raw_sql_response:
                            status.update(label="⚠️ Data Not Available", state="complete", expanded=False)
                            decline_msg = "I am sorry, but the requested data metric or specific column profile is not available within the database schema context."
                            st.markdown(decline_msg)

                            msg_record = {
                                "role": "assistant",
                                "content": decline_msg,
                                "sql": None, "df": None, "is_followup": False, "chart_cfg": None
                            }
                            st.session_state.messages.append(msg_record)
                            save_message_to_db(current_user_key, "assistant", msg_record)
                            return

                        sql_query = _extract_sql(raw_sql_response)
                        is_valid, validation_error = _validate_sql(sql_query)
                        if not is_valid:
                            status.write("🔧 Attempting structural query repair…")
                            sql_query = _repair_sql(sql_query, validation_error)

                        status.write("🗄️ Executing query against database…")
                        conn = get_pooled_connection()
                        try:
                            try:
                                result_df = pd.read_sql_query(sql_query, conn)
                            except (psycopg2.Error, pd.errors.DatabaseError) as db_err:
                                if hasattr(conn, "rollback"):
                                    conn.rollback()
                                status.write("🔄 Database rejected syntax. Running auto-repair loop…")
                                repaired_sql = _repair_sql(sql_query, str(db_err))
                                rep_valid, rep_err = _validate_sql(repaired_sql)
                                if not rep_valid:
                                    raise Exception(f"Post-repair structural guardrail violation: {rep_err}")
                                sql_query = repaired_sql
                                result_df = pd.read_sql_query(sql_query, conn)
                        finally:
                            release_pooled_connection(conn)

                    else:
                        # ── BRANCH B: FOLLOW-UP ON EXISTING DATA ────────────
                        status.write("💬 Processing follow-up on current dataset…")
                        sql_query = last_assistant.get("sql") if last_assistant else None
                        result_df = pd.DataFrame(last_assistant.get("df") or []) if last_assistant else pd.DataFrame()

                    if result_df is None or result_df.empty:
                        status.update(label="⚠️ No results returned", state="complete", expanded=False)
                        no_results_msg = "No matching metrics or database records were returned for this inquiry."
                        st.markdown(no_results_msg)

                        msg_record = {
                            "role": "assistant",
                            "content": no_results_msg,
                            "sql": sql_query, "df": None, "is_followup": not generate_new_sql, "chart_cfg": None
                        }
                        st.session_state.messages.append(msg_record)
                        save_message_to_db(current_user_key, "assistant", msg_record)
                        return

                    # ── PASS 2: NL SUMMARY & BEST PRACTICE CHART PLANNER ───
                    status.write("📝 Generating executive insight summary…")
                    data_preview = result_df.head(15).to_markdown(index=False)
                    
                    # 🛠️ DYNAMIC ROUTING RULES FOR SYSTEM CONTEXT
                    if generate_new_sql:
                        system_prompt_context = VISUALIZATION_SYSTEM_PROMPT
                        user_prompt_content = f"User Request: {user_query}\n\nCurrent Active Data Context:\n{data_preview}"
                    else:
                        # Advanced Analytical Persona for Creative, Proactive Discussions
                        system_prompt_context = (
                            "You are a principal business value and forensic data analyst. "
                            "The user is asking a follow-up question regarding an active dataset.\n\n"
                            "CRITICAL INSTRUCTIONS:\n"
                            "• Avoid passive restatements (e.g., do not just repeat 'the total is X').\n"
                            "• Inject creative business intelligence: interpret *why* an anomaly might occur.\n"
                            "• Connect data points to operational impact (e.g., fraud mitigation, customer friction).\n"
                            "• Structure your response into 3-4 highly engaging, analytical bullets.\n"
                            "• STRICTLY FORBIDDEN: Do not write section titles, numbers, character banners, or ASCII dividers (e.g., '━━━━').\n"
                            "• Do NOT generate any JSON or chart configuration blocks."
                        )
                        user_prompt_content = (
                            f"User Follow-up Request: {user_query}\n\n"
                            f"Active Dataset Reference Context:\n{data_preview}"
                        )

                    summary_payload = [{"role": "system", "content": system_prompt_context}]
                    
                    # Pull past user/assistant textual interactions for context (skipping raw data payloads to save tokens)
                    for historical_msg in st.session_state.get("messages", [])[-4:]:  # Lookback last 4 turns
                        summary_payload.append({
                            "role": historical_msg["role"],
                            "content": historical_msg["content"]
                        })
                    
                    # Append current active turn
                    summary_payload.append({"role": "user", "content": user_prompt_content})

                    summary_completion = client.chat.completions.create(
                        model=GROQ_SUMMARY_MODEL,
                        messages=summary_payload, 
                        temperature=0.4,         
                        max_tokens=600,
                    )
                    raw_summary_response = summary_completion.choices[0].message.content

                    if hasattr(summary_completion, "usage") and summary_completion.usage:
                        total_prompt_tokens += summary_completion.usage.prompt_tokens
                        total_completion_tokens += summary_completion.usage.completion_tokens

                    # Only attempt regex structural parsing if we actually expected a chart payload block
                    if generate_new_sql:
                        json_match = re.search(r"```json\s+(.*?)\s+```", raw_summary_response, re.DOTALL)
                        chart_cfg = json.loads(json_match.group(1).strip()) if json_match else {"chart_type": "none"}
                        assistant_summary = re.sub(r"```json.*?```", "", raw_summary_response, flags=re.DOTALL).strip()
                    else:
                        chart_cfg = {"chart_type": "none"}
                        assistant_summary = raw_summary_response.strip()

                    status.update(
                        label="✅ Analysis completed" if generate_new_sql else "✅ Response completed",
                        state="complete",
                        expanded=False,
                    )

                    # ── Build Message Payload ──────
                    msg_record: dict = {
                        "role": "assistant",
                        "content": assistant_summary,
                        "sql": sql_query if generate_new_sql else None,
                        "df": result_df.to_dict(orient="records") if generate_new_sql else None,
                        "is_followup": not generate_new_sql,
                        "chart_cfg": chart_cfg
                    }

                    # Render live UI components
                    render_assistant_turn(msg_record)

                    # Commit assistant summary and config matrices directly into isolated Postgres store
                    st.session_state.messages.append(msg_record)
                    save_message_to_db(current_user_key, "assistant", msg_record)

                    # Log general internal dashboard diagnostic analytics metrics
                    log_chatbot_interaction(
                        user_query=user_query,
                        sql_query=sql_query,
                        result_df=result_df,
                        assistant_summary=assistant_summary,
                        user_key=current_user_key,
                        username=current_username,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens
                    )

                except Exception as e:
                    status.update(label="❌ Pipeline error", state="error", expanded=False)
                    err_msg = "An unexpected pipeline error occurred. Please clear history and try again."
                    st.error(err_msg)
                    with st.expander("🔬 Technical Error Traceback (Debug Mode)", expanded=True):
                        st.exception(e)
                        if sql_query:
                            st.markdown("**Generated SQL leading to error:**")
                            st.code(sql_query, language="sql")

                    msg_record = {
                        "role": "assistant", "content": err_msg, "sql": sql_query,
                        "df": None, "is_followup": False, "chart_cfg": None
                    }
                    st.session_state.messages.append(msg_record)
                    save_message_to_db(current_user_key, "assistant", msg_record)
                    return