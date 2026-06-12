"""
Analytics AI Chatbot — Tab 3.

Provides a natural-language interface to the curated data warehouse schema
via Groq-powered SQL generation and NL summarisation.

Structure:
  1. Constants & config      — schema context, system prompts, guard-lists
  2. SQL pipeline helpers    — _extract_sql, _validate_sql, _repair_sql
  3. Rendering helpers       — _render_chart
  4. Core pipeline           — _run_query_pipeline
  5. Public entry-point      — render_chatbot_tab
"""

from __future__ import annotations

import re
import pandas as pd
import psycopg2
import streamlit as st

from ai.groq_client import get_groq_client
from config.settings import (
    GROQ_API_KEY,
    GROQ_REPAIR_MODEL,
    GROQ_SQL_MODEL,
    GROQ_SUMMARY_MODEL,
)
from database.connection import get_pooled_connection, release_pooled_connection
from database.transaction_repository import log_chatbot_interaction


# ── 1. Constants & Config ──────────────────────────────────────────────────

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
- JOIN the fact table to dimensions using Business Keys (e.g., `ft.location_id = dl.location_id`),
  NOT surrogate keys (_sk).

STRICT JOIN RULES — VIOLATIONS WILL BREAK THE QUERY:
- Each dimension table (dim_customer, dim_account, dim_device, dim_location) must appear AT MOST
  ONCE in the FROM/JOIN clause. Never join the same table to itself.
- Only join a dimension table if you actually need a column from it in SELECT, WHERE, or GROUP BY.
- The fact table (fact_transactions) is the only driving table. All joins flow FROM it TO dimensions.
- Never chain dimension-to-dimension joins. A dimension must always join directly to fact_transactions.
- POSTGRES COMPLIANCE: Any column in the SELECT clause that is not part of an aggregate function
  MUST be included in the GROUP BY clause exactly as specified.

TIME-SERIES EXTRACTION RULES:
- When grouping by parts of a date (e.g., month, year), use standard PostgreSQL extraction
  functions like `EXTRACT(MONTH FROM ft.transaction_date)` or
  `DATE_TRUNC('month', ft.transaction_date)`.

CRITICAL EXAMPLES:
BAD:
JOIN curated.dim_device dd ON ft.device_id = dd.device_id
JOIN curated.dim_device dtd ON ft.device_id = dtd.device_id

GOOD:
JOIN curated.dim_device dd ON ft.device_id = dd.device_id

Use aliases everywhere in: SELECT, WHERE, GROUP BY, ORDER BY.

QUERY COMPLEXITY RULES:
- Use the minimum number of tables necessary to answer the question.
- If the answer can be derived entirely from fact_transactions columns, do not join any dimension.

ONE-SHOT EXAMPLE:
Question: "What is the total transaction amount by merchant category?"
Correct SQL:
```sql
SELECT
    dl.merchant_category,
    SUM(ft.amount) AS total_transaction_amount
FROM curated.fact_transactions ft
JOIN curated.dim_location dl
    ON ft.location_id = dl.location_id
   AND dl.is_current = true
GROUP BY dl.merchant_category
ORDER BY total_transaction_amount DESC;
```

OUTPUT GUIDELINES:
Respond ONLY with the executable SQL query inside a markdown code block (```sql ... ```).
Do not include any text, explanation, or commentary outside the code block.
"""

_KNOWN_DIMENSION_TABLES: list[str] = [
    "dim_customer",
    "dim_account",
    "dim_device",
    "dim_location",
]

_BLOCKED_KEYWORDS: list[str] = [
    "drop", "delete", "update", "insert", "truncate",
    "alter", "create", "grant", "revoke",
]


# ── 2. SQL Pipeline Helpers ────────────────────────────────────────────────

def _extract_sql(text: str) -> str:
    """Pull the raw SQL string out of a markdown code block."""
    match = re.search(r"```sql\s+(.*?)\s+```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def _validate_sql(sql: str) -> tuple[bool, str]:
    """
    Run lightweight structural checks before executing against the database.

    Returns:
        (True, "")               — query passed all checks.
        (False, reason_string)   — query failed; reason describes the violation.
    """
    sql_lower = sql.lower().strip()

    if not (sql_lower.startswith("select") or sql_lower.startswith("with")):
        return False, "Only read-only SELECT or WITH (CTE) queries are permitted."

    for kw in _BLOCKED_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_lower):
            return False, (
                f"Blocked keyword detected: `{kw.upper()}`. "
                "Only SELECT/WITH queries are allowed."
            )

    join_pattern = re.compile(r"(?:from|join)\s+(?:curated\.)?(\w+)", re.IGNORECASE)
    table_counts: dict[str, int] = {}
    for tbl in join_pattern.findall(sql_lower):
        table_counts[tbl] = table_counts.get(tbl, 0) + 1

    for dim in _KNOWN_DIMENSION_TABLES:
        count = table_counts.get(dim, 0)
        if count > 1:
            return (
                False,
                f"The generated SQL joins `{dim}` {count} times. "
                "This is a self-join hallucination — each dimension table may only appear once.",
            )

    return True, ""


def _repair_sql(sql: str, validation_error: str) -> str:
    """
    Ask the repair model to fix a structurally invalid SQL query.

    Preserves original business intent while removing violating constructs.
    Falls back to the original SQL if the Groq client is unavailable.
    """
    client = get_groq_client()
    if not client:
        return sql

    repair_prompt = (
        "You are a PostgreSQL expert.\n\n"
        "The following SQL violates schema rules.\n\n"
        f"Validation Error:\n{validation_error}\n\n"
        "Rules:\n"
        "- Each dimension table may appear only once.\n"
        "- Remove duplicate joins.\n"
        "- Preserve the original business intent.\n"
        "- Keep all filters and aggregations intact.\n"
        "- Return ONLY executable SQL inside a ```sql block.\n\n"
        f"SQL:\n{sql}"
    )

    response = client.chat.completions.create(
        model=GROQ_REPAIR_MODEL,
        messages=[{"role": "user", "content": repair_prompt}],
        temperature=0,
    )
    return _extract_sql(response.choices[0].message.content)


# ── 3. Rendering Helpers ───────────────────────────────────────────────────

def _render_chart(df: pd.DataFrame) -> None:
    """
    Intelligently identifies the best categorical axis (X) and numeric metric (Y)
    from the DataFrame to render a clean, high-value bar chart.
    """
    # 1. Isolate numeric columns, filtering out obvious surrogate keys or numeric IDs
    all_numeric = df.select_dtypes(include="number").columns.tolist()
    numeric_cols = [
        col for col in all_numeric 
        if not any(ign in col.lower() for ign in ["_sk", "id", "number", "postal", "zip"])
    ]
    
    # Fallback to all numeric if everything got filtered out (prevent breaking)
    if not numeric_cols and all_numeric:
        numeric_cols = all_numeric

    if not numeric_cols:
        return  # No valid metrics to plot

    # 2. Score and pick the best Y-axis (Metric)
    # Prioritize sum totals, amounts, counts, and averages over raw codes
    def score_y_column(col_name: str) -> int:
        c = col_name.lower()
        if "amount" in c or "value" in c or "total" in c or "sum" in c:
            return 10
        if "count" in c or "rate" in c or "pct" in c or "percentage" in c:
            return 8
        if "time" in c or "ms" in c or "duration" in c:
            return 5
        return 0

    y_axis = max(numeric_cols, key=score_y_column)
    clean_y = y_axis.replace("_", " ").title()

    # 3. Score and pick the best X-axis (Dimension)
    # Exclude numeric column used for Y, and find the best descriptive column
    remaining_cols = [col for col in df.columns if col != y_axis]
    
    def score_x_column(col_name: str) -> int:
        c = col_name.lower()
        # High priority for descriptive names/categories
        if "name" in c or "category" in c or "type" in c or "status" in c:
            return 10
        if "occupation" in c or "channel" in c or "device" in c or "browser" in c:
            return 9
        if "city" in c or "state" in c or "country" in c:
            return 8
        if "date" in c or "month" in c or "year" in c:
            return 7
        # Low priority for IDs even if they are strings
        if "id" in c or "sk" in c:
            return -5
        return 0

    col, _ = st.columns([2, 1])

    if not remaining_cols:
        st.write(f"📊 **{clean_y} (by row index)**")
        with col:
            st.bar_chart(df[y_axis], use_container_width=True, y_label=clean_y)
        return

    x_axis = max(remaining_cols, key=score_x_column)
    clean_x = x_axis.replace("_", " ").title()
    
    # 4. Final verification: If the chosen X-axis is an ID or completely numeric, 
    # check if we can truncate the data length to prevent crowded UI crashing.
    plot_df = df.set_index(x_axis)[y_axis]
    if len(plot_df) > 20:
        plot_df = plot_df.head(20) # Keep the chart clean and performant

    st.write(f"📊 **{clean_y} by {clean_x}**")
    with col:
        st.bar_chart(
            plot_df,
            use_container_width=True,
            x_label=clean_x,
            y_label=clean_y,
        )


# ── 4. Core Pipeline ───────────────────────────────────────────────────────

def _run_query_pipeline(user_query: str, container) -> None:
    """
    Execute the full analytics pipeline for a single user question.

    Stages:
      1. Build the LLM message payload (system prompt + conversation history).
      2. Pass 1 — SQL generation via GROQ_SQL_MODEL.
      3. Structural validation; repair if invalid.
      4. Database execution; auto-repair on DB-level syntax error.
      5. Pass 2 — NL executive summary via GROQ_SUMMARY_MODEL.
      6. Render expanders, chart, and insight markdown inside `container`.
      7. Persist interaction to the transaction log and session state.

    Args:
        user_query: The raw natural-language question from the user.
        container:  The Streamlit container to render all output into.
    """
    client = get_groq_client()
    if not client:
        with container:
            st.error("🔑 Groq API key missing — add GROQ_API_KEY to .streamlit/secrets.toml.")
        return

    # Build conversation payload (system prompt + prior turns + current question)
    llm_payload = [{"role": "system", "content": SQL_SYSTEM_PROMPT}]
    for msg in st.session_state.get("messages", [])[:-1]:
        if msg.get("role") in ("user", "assistant"):
            llm_payload.append({"role": msg["role"], "content": msg["content"]})
    llm_payload.append({"role": "user", "content": user_query})

    with container:
        with st.chat_message("assistant"):
            with st.status("Processing Analytics Request…", expanded=True) as status:
                sql_query: str | None = None
                try:
                    # Pass 1 — SQL generation
                    status.write("🧠 Generating SQL query…")
                    completion = client.chat.completions.create(
                        model=GROQ_SQL_MODEL,
                        messages=llm_payload,
                        temperature=0.0,
                        max_tokens=600,
                    )
                    sql_query = _extract_sql(completion.choices[0].message.content)

                    # Pre-execution structural verification
                    is_valid, validation_error = _validate_sql(sql_query)
                    if not is_valid:
                        status.write("🔧 Attempting structural query repair…")
                        sql_query = _repair_sql(sql_query, validation_error)

                    # Database execution
                    status.write("🗄️ Executing query against database…")
                    conn = get_pooled_connection()
                    try:
                        try:
                            result_df = pd.read_sql_query(sql_query, conn)
                        except (psycopg2.Error, pd.errors.DatabaseError) as db_err:
                            if hasattr(conn, "rollback"):
                                conn.rollback()

                            status.write("🔄 Database rejected syntax. Running auto-repair loop…")
                            sql_query = _repair_sql(sql_query, str(db_err))

                            rep_valid, rep_err = _validate_sql(sql_query)
                            if not rep_valid:
                                raise Exception(
                                    f"Post-repair structural guardrail violation: {rep_err}"
                                )

                            result_df = pd.read_sql_query(sql_query, conn)
                    finally:
                        release_pooled_connection(conn)

                    if result_df.empty:
                        status.update(
                            label="⚠️ Query returned zero rows",
                            state="error",
                            expanded=False,
                        )
                        msg = "The query executed successfully but returned no matching rows."
                        st.info(msg)
                        with st.expander("🛠️ View Compiled Execution Query", expanded=False):
                            st.code(sql_query, language="sql")
                        log_chatbot_interaction(user_query, sql_query, None, msg)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": msg, "sql": sql_query, "df": None}
                        )
                        return

                    # Pass 2 — NL summary
                    status.write("📝 Generating executive insight summary…")
                    data_preview = result_df.head(15).to_markdown(index=False)
                    summary_completion = client.chat.completions.create(
                        model=GROQ_SUMMARY_MODEL,
                        messages=[{
                            "role": "system",
                            "content": (
                                "You are an experienced business analyst. "
                                "Explain the results simply.\n\n"
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

                    status.update(
                        label="✅ Analysis completed",
                        state="complete",
                        expanded=False,
                    )

                    # Render results
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
                    err_msg = (
                        "An unexpected pipeline error occurred. "
                        "Please clear history and try again."
                    )
                    st.error(err_msg)
                    with st.expander("🔬 Technical Error Traceback (Debug Mode)", expanded=True):
                        st.exception(e)
                        if sql_query:
                            st.markdown("**Generated SQL leading to error:**")
                            st.code(sql_query, language="sql")

                    log_chatbot_interaction(user_query, sql_query, None, str(e))
                    st.session_state.messages.append(
                        {"role": "assistant", "content": err_msg, "sql": sql_query, "df": None}
                    )


# ── 5. Public Entry-Point ──────────────────────────────────────────────────

# Injected CSS that turns Streamlit's default layout into a proper chat UI:
#
#   • Hides the default page top-padding so the chat feed starts flush.
#   • Pins st.chat_input to the bottom of the viewport at all times.
#   • Gives the scrollable message feed enough bottom padding so the last
#     message is never hidden behind the fixed input bar.
#   • Removes the fixed-height cap on the st.container so the feed grows
#     naturally and the browser scroll handles overflow instead.
#   • Tightens avatar spacing and aligns bubbles closer to how modern chat
#     apps lay out turns (user right, assistant left).

_CHAT_UI_CSS = """
<style>
.block-container {
    padding-top: 0.5rem !important;
    padding-bottom: 0rem !important;
}
.chat-header {
    padding: 0.5rem 0 0.5rem 0;
    border-bottom: 1px solid rgba(128,128,128,0.15);
    margin-bottom: 0.75rem;
}
div[data-testid="stChatMessage"] {
    padding: 0.5rem 0.5rem !important;
    border-radius: 12px !important;
    margin-bottom: 0.4rem !important;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: rgba(99, 102, 241, 0.05) !important;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: rgba(128, 128, 128, 0.04) !important;
}

/* ── CRITICAL FIX FOR CLIPPING ── */
/* Adds an invisible spatial buffer zone at the bottom of the scroll container */
div[data-testid="stVContainer"] {
    padding-bottom: 70px !important;
}

.chat-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 30vh;
    opacity: 0.45;
    gap: 0.5rem;
}
</style>
"""


def render_chatbot_tab() -> None:
    """
    Render the full Analytics AI Chatbot interface inside Tab 3.

    UI layout:
      - Injected CSS pins the chat input to the bottom of the viewport.
      - Message history fills the remaining vertical space and scrolls naturally.
      - An empty-state hint is shown when no messages exist yet.
      - Sidebar carries engine metadata, connection status, and clear-history.
    """
    # Inject chat UI styles once per render
    st.markdown(_CHAT_UI_CSS, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    _render_sidebar()

    # Compact header (replaces st.header to avoid excess vertical space)
    st.markdown(
        '<div class="chat-header">'
        '<strong>💳 Banking Transactions Analytics</strong>&nbsp;&nbsp;'
        '<span style="font-size:0.82rem;opacity:0.55;">'
        'Ask anything about transactions, accounts, fraud patterns, and more.'
        '</span></div>',
        unsafe_allow_html=True,
    )

    # Use an unbounded container so messages stack naturally and the page
    # scroll (not a fixed-height inner scroll) handles overflow.
    chat_container = st.container()
    _render_history(chat_container)

    # Fixed-bottom chat input (styled via CSS above)
    if user_query := st.chat_input("Ask anything about your transactions…"):
        st.session_state.messages.append({"role": "user", "content": user_query})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_query)
        _run_query_pipeline(user_query, chat_container)


def _render_sidebar() -> None:
    """Populate the sidebar with engine metadata and session controls."""
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


def _render_history(chat_container) -> None:
    """
    Replay all stored messages into the chat container.

    Shows an empty-state prompt when no messages exist yet.
    For assistant turns, also re-renders the SQL expander, data expander,
    and chart so history is fully interactive.
    """
    with chat_container:
        if not st.session_state.messages:
            st.markdown(
                '<div class="chat-empty-state">'
                '<div class="icon">💬</div>'
                "<p>No messages yet.<br/>Ask a question below to get started.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg.get("role", "assistant")):
                st.markdown(msg.get("content", ""))

                if msg.get("role") != "assistant":
                    continue

                if msg.get("sql"):
                    with st.expander("🛠️ View Compiled Execution Query", expanded=False):
                        st.code(msg["sql"], language="sql")

                stored_df = msg.get("df")
                if stored_df is not None:
                    df_restored = pd.DataFrame(stored_df)
                    if not df_restored.empty:
                        with st.expander("📋 View Result Data", expanded=False):
                            st.dataframe(
                                df_restored,
                                use_container_width=True,
                                key=f"hist_df_{idx}",
                            )
                        _render_chart(df_restored)