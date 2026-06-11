CREATE SCHEMA IF NOT EXISTS ml_predictions;

CREATE TABLE IF NOT EXISTS ml_predictions.transaction_logs(
    id SERIAL PRIMARY KEY, 
    account_id VARCHAR(100),
    device_id VARCHAR(100),
    location_id VARCHAR(100),
    transaction_type VARCHAR(50),
    channel VARCHAR(50),
    amount NUMERIC(12, 2),
    currency VARCHAR(10),
    transaction_status VARCHAR(50),
    merchant_category VARCHAR(100),
    transaction_date DATE,
    transaction_time TIME,
    processing_time_ms INT,
    fraud_probability NUMERIC(5, 4),
    prediction INT,
    risk_category VARCHAR(50),
    blacklisted_account BOOLEAN DEFAULT FALSE,
	fraud_source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);