--Tables

--Table 1 - fraud_kpi_summary
CREATE SCHEMA IF NOT EXISTS aggregated;

CREATE TABLE IF NOT EXISTS aggregated.fraud_kpi_summary (
    id INT PRIMARY KEY DEFAULT 1,
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_rate NUMERIC(5,2),
    fraud_amount NUMERIC(18,2),
    avg_transaction_amount NUMERIC(18,2),
    last_updated TIMESTAMP DEFAULT NOW()
);

--Table 2 - fraud_trend

CREATE TABLE IF NOT EXISTS aggregated.fraud_trend (
    transaction_date DATE PRIMARY KEY,
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_amount NUMERIC(18,2),
    fraud_rate NUMERIC(5,2),
    last_updated TIMESTAMP DEFAULT NOW()
);

--Table 4 - geo_fraud_summary

CREATE TABLE IF NOT EXISTS aggregated.geo_fraud_summary (
    country VARCHAR(100),
    state VARCHAR(100),
    city VARCHAR(100),
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_amount NUMERIC(18,2),
    fraud_rate NUMERIC(5,2),
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (country, state, city)
);


--Table 6 - Customer_risk_summary

CREATE TABLE IF NOT EXISTS aggregated.customer_risk_summary (
    customer_id VARCHAR(50) PRIMARY KEY,
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_amount NUMERIC(18,2),
    fraud_rate NUMERIC(5,2),
    avg_transaction NUMERIC(18,2),
    max_transaction NUMERIC(18,2),
    last_updated TIMESTAMP DEFAULT NOW()
);


--Table 8 - device_risk_summary

CREATE TABLE IF NOT EXISTS aggregated.device_risk_summary (
    device_type VARCHAR(50),
    is_trusted BOOLEAN,
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_rate NUMERIC(5,2),
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (device_type, is_trusted)
);


--VIEWS

--amount_distribution

CREATE OR REPLACE VIEW aggregated.amount_distribution AS
SELECT
CASE
    WHEN amount < 100 THEN '0-100'
    WHEN amount < 500 THEN '100-500'
    WHEN amount < 1000 THEN '500-1000'
    WHEN amount < 5000 THEN '1000-5000'
    ELSE '5000+'
END AS amount_bucket,
COUNT(*) total_transactions,
COUNT(*) FILTER (WHERE is_fraud) fraud_transactions,
ROUND(
COUNT(*) FILTER (WHERE is_fraud)::numeric / COUNT(*) * 100,2
) fraud_rate
FROM curated.fact_transactions
GROUP BY 1;

--transaction_investigration_view
CREATE OR REPLACE VIEW aggregated.transaction_investigation_view AS
SELECT
    ft.transaction_id,
    ft.transaction_date,
    ft.customer_id,
    dc.full_name,
    dl.merchant_name,
    dl.merchant_category,
    dl.city,
    dl.state,
    ft.channel,
    dd.device_type,
    dd.is_trusted,
    ft.amount,
    ft.is_fraud
FROM curated.fact_transactions ft
LEFT JOIN curated.dim_customer dc
    ON ft.customer_id = dc.customer_id
    AND dc.is_current = true
LEFT JOIN curated.dim_location dl
    ON ft.location_id = dl.location_id
    AND dl.is_current = true
LEFT JOIN curated.dim_device dd
    ON ft.device_id = dd.device_id
    AND dd.is_current = true;

CREATE TABLE aggregated.merchant_risk_summary (
    merchant_name VARCHAR(200),
    merchant_category VARCHAR(100),
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_amount NUMERIC(18,2),
    fraud_rate NUMERIC(5,2),
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (merchant_name, merchant_category)
);

CREATE OR REPLACE VIEW aggregated.fraud_day_heatmap AS
SELECT
    EXTRACT(DOW FROM transaction_date) AS dow,
    TRIM(TO_CHAR(transaction_date,'Day')) AS weekday,
    COUNT(*) AS total_transactions,
    COUNT(*) FILTER (WHERE is_fraud = true) AS fraud_transactions
FROM curated.fact_transactions
GROUP BY 1,2;

CREATE TABLE IF NOT EXISTS aggregated.fraud_by_mcc (
    merchant_category VARCHAR(100) PRIMARY KEY,
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_amount NUMERIC(18,2),
    fraud_rate NUMERIC(5,2),
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aggregated.channel_fraud_summary (
    channel VARCHAR(50) PRIMARY KEY,
    total_transactions BIGINT,
    fraud_transactions BIGINT,
    fraud_amount NUMERIC(18,2),
    fraud_rate NUMERIC(5,2),
    last_updated TIMESTAMP DEFAULT NOW()
);