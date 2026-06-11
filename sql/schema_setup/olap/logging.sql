

-- logging schema
CREATE SCHEMA IF NOT EXISTS logging;

-- PIPELINE LOGS TABLE

CREATE TABLE IF NOT EXISTS logging.pipeline_logs (
    log_id              SERIAL PRIMARY KEY,
    service             VARCHAR(50),        -- 'fastapi' or 'airflow'
    log_level           VARCHAR(10),        -- INFO, WARNING, ERROR
    event_type          VARCHAR(50),        -- INSERT, UPDATE, DELETE, DAG_RUN, ERROR
    table_name          VARCHAR(100),       -- which table was affected
    record_id           VARCHAR(100),       -- primary key of the record
    message             TEXT,               -- log message
    error_details       TEXT,               -- error traceback if any
    rows_affected       INTEGER,            -- how many rows were processed
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_logs_service 
    ON logging.pipeline_logs(service);

CREATE INDEX IF NOT EXISTS idx_pipeline_logs_created_at 
    ON logging.pipeline_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_pipeline_logs_log_level 
    ON logging.pipeline_logs(log_level);

