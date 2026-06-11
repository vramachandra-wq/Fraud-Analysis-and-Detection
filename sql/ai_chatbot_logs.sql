CREATE TABLE IF NOT EXISTS curated.ai_chatbot_logs (
    log_id            BIGSERIAL PRIMARY KEY,
    prompt            TEXT NOT NULL,
    sql_code          TEXT,
    generated_table   JSONB,                  -- Stores data rows as a structural JSON array
    ai_summary        TEXT,
    created_at        TIMESTAMP DEFAULT NOW() -- Tracks exactly when the query ran
);

CREATE INDEX idx_chatbot_logs_created ON curated.ai_chatbot_logs(created_at DESC);