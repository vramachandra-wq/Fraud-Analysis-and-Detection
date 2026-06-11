"""
Analytics AI Chatbot — Tab 3.

Provides a natural-language interface to the curated data warehouse schema
via Groq-powered SQL generation and NL summarisation.
"""

import re
import pandas as pd
import streamlit as st

from ai.groq_client import get_groq_client
from database.connection import get_pooled_connection, release_pooled_connection
from database.transaction_repository import log_chatbot_interaction
from config.settings import GROQ_SQL_MODEL, GROQ_REPAIR_MODEL, GROQ_SUMMARY_MODEL, GROQ_API_KEY


# ── Schema & prompt constants ──────────────────────────────────────────────

SCHEMA_CONTEXT = """
Schema: curated
Tables:
1. curated.dim_customer (SCD Type 2)
   - dim_customer_sk (BIGSERIAL, PK), customer_id (VARCHAR, Business Key), full_name,
     email, phone, date_of_birth, gender, nationality, city, state, country, occupation,
     credit_score, annual_income, is_active, is_current (BOOLEAN)
2. curated.dim_account (SCD Type 2)
   - dim_account_sk (BIGSERIAL, PK), account_id (VARCHAR, Business Key), customer_id,
     account_number, account_type, account_status, bank_name, currency, balance,
     credit_limit, is_current (BOOLEAN)
3. curated.dim_device (SCD Type 2)
   - dim_device_sk (BIGSERIAL, PK), device_id (VARCHAR, Business Key), customer_id,
     device_type, operating_system, browser, ip_address, is_trusted, is_current (BOOLEAN)
4. curated.dim_location (SCD Type 2)
   - dim_location_sk (BIGSERIAL, PK), location_id (VARCHAR, Business Key), merchant_name,
     merchant_category, city, state, country, latitude, longitude,
     is_high_risk_area, is_current (BOOLEAN)
5. curated.fact_transactions (Fact Table)
   - transaction_id (VARCHAR, PK), account_id, customer_id, device_id, location_id,
     transaction_type, channel, amount (NUMERIC), currency, transaction_status,
     is_fraud (BOOLEAN), fraud_reason, transaction_date (DATE), transaction_time (TIME),
     processing_time_ms (INTEGER)
"""

SQL_SYSTEM_PROMPT = f"""
You are an expert data analyst converting user questions into precise PostgreSQL queries.
Given the database schema below, write a SQL query that answers the user's request.

{SCHEMA_CONTEXT}

CRITICAL SCD TYPE 2 INSTRUCTIONS:
- Unless explicitly asked otherwise, ALWAYS filter dimension tables with `is_current = true`.
  Apply the filter as part of the JOIN condition, e.g.:
  JOIN curated.dim_location dl ON ft.location_id = dl.location_id AND dl.is_current = true
- JOIN the fact table to dimensions using Business Keys, NOT surrogate keys (_sk).

STRICT JOIN RULES — VIOLATIONS WILL BREAK THE QUERY:
- Each dimension table must appear AT MOST ONCE in the FROM/JOIN clause.
- Only join a dimension table if you actually need a column from it.
- The fact table (fact_transactions) is the only driving table.
- Never chain dimension-to-dimension joins.

Use aliases everywhere in SELECT, WHERE, GROUP BY, ORDER BY.
Use the minimum number of tables necessary to answer the question.

OUTPUT GUIDELINES:
- Respond ONLY with the executable SQL query inside a markdown code block (```sql ... ```).
- Do not include any text, explanation, or commentary outside the code block.
"""

_KNOWN_DIMENSION_TABLES = ["dim_customer", "dim_account", "dim_device", "dim_location"]
_BLOCKED_KEYWORDS = [
    "drop", "delete", "update", "insert", "truncate",
    "alter", "create", "grant", "revoke",
]


# ── SQL helpers ────────────────────────────────────────────────────────────

def _extract_sql(text: str) -> str:
    match = re.search(r"```sql\s+(.*?)\s+```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def _validate_sql(sql: str) -> tuple[bool, str]:
    sql_lower = sql.lower().strip()

    if not sql_lower.startswith("select"):
        return False, "Only SELECT queries are permitted."

    for kw in _BLOCKED_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_lower):
            return False, f"Blocked keyword detected: `{kw.upper()}`. Only SELECT queries are allowed."

    join_pattern = re.compile(r"(?:from|join)\s+(?:curated\.)?(\w+)", re.IGNORECASE)
    table_counts: dict[str, int] = {}
    for tbl in join_pattern.findall(sql_lower):
        table_counts[tbl] = table_counts.get(tbl, 0) + 1

    for dim in _KNOWN_DIMENSION_TABLES:
        if table_counts.get(dim, 0) > 1:
            return (
                False,
                f"The query joins `{dim}` more than once. "
                "Each dimension table may only appear once.",
            )

    return True, ""


def _repair_sql(sql: str, error: str) -> str:
    client = get_groq_client()
    if not client:
        return sql
    repair_prompt = (
        "You are a PostgreSQL expert.\n\n"
        "The following SQL violates schema rules.\n\n"
        f"Validation Error:\n{error}\n\n"
        "Rules:\n"
        "- Each dimension table may appear only once.\n"
        "- Remove duplicate joins.\n"
        "- Preserve the original business intent.\n"
        "- Return ONLY executable SQL inside a ```sql block.\n\n"
        f"SQL:\n{sql}"
    )
    response = client.chat.completions.create(
        model=GROQ_REPAIR_MODEL,
        messages=[{"role": "user", "content": repair_prompt}],
        temperature=0,
    )
    return _extract_sql(response.choices[0].message.content)


def _render_chart(df: pd.DataFrame) -> None:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric_cols = df.select_dtypes(exclude="number").columns.tolist()
    if not numeric_cols:
        return

    y_axis = numeric_cols[0]
    clean_y = y_axis.replace("_", " ").title()

    if not non_numeric_cols:
        st.write(f"📊 **{clean_y} (by row index)**")
        col, _ = st.columns([1, 1])
        with col:
            st.bar_chart(df[y_axis], use_container_width=True, y_label=clean_y)
        return

    x_axis = non_numeric_cols[0]
    clean_x = x_axis.replace("_", " ").title()
    st.write(f"📊 **{clean_y} by {clean_x}**")
    col, _ = st.columns([1, 1])
    with col:
        st.bar_chart(
            df.set_index(x_axis)[y_axis],
            use_container_width=True,
            x_label=clean_x,
            y_label=clean_y,
        )


# ── Main pipeline ──────────────────────────────────────────────────────────

def _run_query_pipeline(user_query: str) -> None:
    client = get_groq_client()
    if not client:
        st.error("🔑 Groq API key missing — add `GROQ_API_KEY` to `.streamlit/secrets.toml`.")
        return

    llm_payload = [{"role": "system", "content": SQL_SYSTEM_PROMPT}]
    for msg in st.session_state.messages[:-1]:
        llm_payload.append({"role": msg["role"], "content": msg["content"]})
    llm_payload.append({"role": "user", "content": user_query})

    with st.chat_message("assistant"):
        with st.status("Processing Analytics Request…", expanded=True) as status:
            sql_query: str | None = None
            try:
                # Pass 1 – SQL generation
                status.write("🧠 Generating SQL query…")
                completion = client.chat.completions.create(
                    model=GROQ_SQL_MODEL,
                    messages=llm_payload,
                    temperature=0.0,
                    max_tokens=600,
                )
                sql_query = _extract_sql(completion.choices[0].message.content)

                is_valid, validation_error = _validate_sql(sql_query)
                if not is_valid:
                    status.write("🔧 Attempting query repair…")
                    repaired = _repair_sql(sql_query, validation_error)
                    repaired_valid, repaired_error = _validate_sql(repaired)
                    if repaired_valid:
                        sql_query = repaired
                    else:
                        status.update(label="⚠️ Query validation failed", state="error", expanded=False)
                        st.error(validation_error)
                        with st.expander("🛠️ View Generated Query", expanded=False):
                            st.code(sql_query, language="sql")
                        log_chatbot_interaction(user_query, sql_query, None, f"BLOCKED: {validation_error}")
                        st.session_state.messages.append(
                            {"role": "assistant", "content": f"⚠️ {validation_error}", "sql": sql_query, "df": None}
                        )
                        return

                # Database execution
                status.write("🗄️ Executing query against database…")
                conn = get_pooled_connection()
                try:
                    result_df = pd.read_sql_query(sql_query, conn)
                finally:
                    release_pooled_connection(conn)

                if result_df.empty:
                    status.update(label="⚠️ Query returned zero rows", state="error", expanded=False)
                    msg = "The query executed successfully but returned no matching rows."
                    st.info(msg)
                    with st.expander("🛠️ View Compiled Execution Query", expanded=False):
                        st.code(sql_query, language="sql")
                    log_chatbot_interaction(user_query, sql_query, None, msg)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": msg, "sql": sql_query, "df": None}
                    )
                    return

                # Pass 2 – NL summary
                status.write("📝 Generating executive insight summary…")
                data_preview = result_df.head(15).to_markdown(index=False)
                summary_completion = client.chat.completions.create(
                    model=GROQ_SUMMARY_MODEL,
                    messages=[{
                        "role": "system",
                        "content": (
                            "You are an experienced business analyst. Explain the results simply.\n\n"
                            "Guidelines:\n"
                            "• Start with a direct answer to the question.\n"
                            "• Highlight key trends or anomalies.\n"
                            "• Avoid technical terms, dataframes, or SQL vocabulary.\n"
                            "• Focus completely on business context.\n"
                            "• Output 3-6 concise bullets.\n\n"
                            f"User Question: {user_query}\n\n"
                            f"Data Summary:\n{data_preview}"
                        ),
                    }],
                    temperature=0.3,
                    max_tokens=400,
                )
                assistant_summary = summary_completion.choices[0].message.content

                status.update(label="✅ Analysis completed", state="complete", expanded=False)

                with st.expander("🛠️ View Compiled Execution Query", expanded=False):
                    st.code(sql_query, language="sql")
                with st.expander("📋 View Result Data", expanded=False):
                    st.dataframe(result_df, use_container_width=True)

                _render_chart(result_df)
                st.markdown("### 📋 Key Insights")
                st.markdown(assistant_summary)

                log_chatbot_interaction(user_query, sql_query, result_df, assistant_summary)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_summary,
                    "sql": sql_query,
                    "df": result_df.to_dict(orient="records"),
                })

            except Exception as e:
                status.update(label="❌ Pipeline error", state="error", expanded=False)
                err_msg = "An unexpected pipeline error occurred. Please clear history and try again."
                st.error(err_msg)
                log_chatbot_interaction(user_query, sql_query, None, str(e))
                st.session_state.messages.append(
                    {"role": "assistant", "content": err_msg, "sql": sql_query, "df": None}
                )


# ── Public entry-point ─────────────────────────────────────────────────────

def render_chatbot_tab() -> None:
    """Render the full Analytics AI Chatbot interface inside Tab 3."""
    st.header("💳 Banking Transactions Analytics Chatbot")
    st.markdown("Ask natural-language questions about transactions, accounts, fraud patterns, and more.")
    st.markdown("---")

    # Sidebar additions (only relevant when this tab is active, but always rendered)
    with st.sidebar:
        st.markdown("---")
        st.markdown("### ⚙️ Analytics Engine")
        st.caption("**Provider:** Groq Cloud Infrastructure")
        st.caption(f"**SQL Model:** `{GROQ_SQL_MODEL}`")
        st.caption(f"**Summary Model:** `{GROQ_SUMMARY_MODEL}`")
        st.markdown("---")
        st.markdown("### 🔌 Connection Status")
        if GROQ_API_KEY:
            st.success("Groq Pipeline: Connected")
        else:
            st.error("Groq Pipeline: Key Missing")
        st.markdown("---")
        if st.button("🗑️ Clear Chat History", use_container_width=True, key="clear_chat_btn"):
            st.session_state.messages = []
            st.rerun()

    # Render historical messages
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                if msg.get("sql"):
                    with st.expander("🛠️ View Compiled Execution Query", expanded=False):
                        st.code(msg["sql"], language="sql")
                stored_df = msg.get("df")
                if stored_df is not None:
                    df_restored = pd.DataFrame(stored_df)
                    if not df_restored.empty:
                        with st.expander("📋 View Result Data", expanded=False):
                            st.dataframe(df_restored, use_container_width=True, key=f"hist_df_{idx}")
                        _render_chart(df_restored)

    # Chat input
    if user_query := st.chat_input("Ask Analytics Queries…"):
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)
        _run_query_pipeline(user_query)
