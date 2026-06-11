CREATE OR REPLACE VIEW curated.vw_fraud_transaction_analytics AS
WITH customer_current AS (
    SELECT *
    FROM (
        SELECT
            dc.*,
            ROW_NUMBER() OVER (
                PARTITION BY dc.customer_id
                ORDER BY dc.valid_from DESC NULLS LAST,
                         dc.dwh_updated_at DESC
            ) AS rn
        FROM curated.dim_customer dc
        WHERE dc.is_current = TRUE
    ) x
    WHERE rn = 1
),

account_current AS (
    SELECT *
    FROM (
        SELECT
            da.*,
            ROW_NUMBER() OVER (
                PARTITION BY da.account_id
                ORDER BY da.valid_from DESC NULLS LAST,
                         da.dwh_updated_at DESC
            ) AS rn
        FROM curated.dim_account da
        WHERE da.is_current = TRUE
    ) x
    WHERE rn = 1
),

device_current AS (
    SELECT *
    FROM (
        SELECT
            dd.*,
            ROW_NUMBER() OVER (
                PARTITION BY dd.device_id
                ORDER BY dd.valid_from DESC NULLS LAST,
                         dd.dwh_updated_at DESC
            ) AS rn
        FROM curated.dim_device dd
        WHERE dd.is_current = TRUE
    ) x
    WHERE rn = 1
),

location_current AS (
    SELECT *
    FROM (
        SELECT
            dl.*,
            ROW_NUMBER() OVER (
                PARTITION BY dl.location_id
                ORDER BY dl.valid_from DESC NULLS LAST,
                         dl.dwh_updated_at DESC
            ) AS rn
        FROM curated.dim_location dl
        WHERE dl.is_current = TRUE
    ) x
    WHERE rn = 1
),

fraud_results AS (
    SELECT *
    FROM curated.fn_analyze_transaction_fraud_2_claude(
        NULL,     -- p_lookback_days (full history)
        1,        -- p_high_val_days
        3,        -- p_high_val_txn_count
        50000,    -- p_high_val_amount_threshold
        1,        -- p_atm_mult_days
        3,        -- p_atm_mult_txn_count
        50000,    -- p_atm_mult_amount_threshold
        24,       -- p_velocity_hours
        2,        -- p_velocity_min_txns
        100,      -- p_velocity_km_threshold
        200,      -- p_velocity_kmh (Max speed parameter)
        10,       -- p_device_minutes_window
        2         -- p_device_min_burst_freq
    )
)

SELECT
    -- =========================================================
    -- FRAUD OUTPUT
    -- =========================================================
    fr.transaction_id,
    fr.customer_id,
    fr.account_id,
    fr.transaction_type,
    fr.channel,
    fr.amount,
    fr.transaction_status,
    fr.transaction_date,
    fr.transaction_time,
    fr.created_at,
    fr.location_id,
    fr.device_id,
    fr.reference_number,
    fr.fraud_flag,
    fr.fraud_reason,

    -- =========================================================
    -- TIMESTAMP
    -- =========================================================
    (fr.transaction_date + fr.transaction_time) AS transaction_timestamp,

    -- =========================================================
    -- CUSTOMER DIMENSION
    -- =========================================================
    dc.full_name,
    dc.email,
    dc.phone,
    dc.date_of_birth,
    dc.gender,
    dc.nationality,
    dc.city AS customer_city,
    dc.state AS customer_state,
    dc.country AS customer_country,
    dc.is_active AS customer_active_flag,
    dc.credit_score,
    dc.annual_income,
    dc.occupation,

    -- =========================================================
    -- ACCOUNT DIMENSION
    -- =========================================================
    da.account_number,
    da.account_type,
    da.account_status,
    da.bank_name,
    da.currency AS account_currency,
    da.balance,
    da.credit_limit,
    da.opening_date,
    da.closing_date,

    -- =========================================================
    -- DEVICE DIMENSION
    -- =========================================================
    dd.device_type,
    dd.operating_system,
    dd.browser,
    dd.ip_address,
    dd.is_trusted,
    dd.first_seen_at,
    dd.last_seen_at,

    -- =========================================================
    -- LOCATION DIMENSION
    -- =========================================================
    dl.merchant_name,
    dl.merchant_category,
    dl.city AS merchant_city,
    dl.state AS merchant_state,
    dl.country AS merchant_country,
    dl.latitude AS merchant_latitude,
    dl.longitude AS merchant_longitude,
    dl.is_high_risk_area AS merchant_is_high_risk_area,

    -- =========================================================
    -- DERIVED ANALYTICS COLUMNS
    -- =========================================================
    EXTRACT(YEAR FROM AGE(CURRENT_DATE, dc.date_of_birth)) AS customer_age,

    CASE
        WHEN fr.amount < 1000 THEN 'LOW'
        WHEN fr.amount BETWEEN 1000 AND 10000 THEN 'MEDIUM'
        WHEN fr.amount BETWEEN 10001 AND 50000 THEN 'HIGH'
        ELSE 'VERY_HIGH'
    END AS transaction_amount_band,

    CASE WHEN LOWER(fr.channel) = 'atm'    THEN TRUE ELSE FALSE END AS atm_transaction_flag,
    CASE WHEN LOWER(fr.channel) = 'online' THEN TRUE ELSE FALSE END AS online_transaction_flag,
    CASE WHEN LOWER(fr.channel) = 'mobile' THEN TRUE ELSE FALSE END AS mobile_transaction_flag,

    CASE
        WHEN EXTRACT(HOUR FROM fr.transaction_time) BETWEEN 0 AND 5 THEN TRUE
        ELSE FALSE
    END AS late_night_transaction_flag,

    CASE
        WHEN dl.is_high_risk_area = TRUE THEN 'HIGH_RISK_LOCATION'
        ELSE 'NORMAL_LOCATION'
    END AS location_risk_band,

    CASE
        WHEN dc.credit_score < 550 THEN 'POOR'
        WHEN dc.credit_score BETWEEN 550 AND 649 THEN 'FAIR'
        WHEN dc.credit_score BETWEEN 650 AND 749 THEN 'GOOD'
        ELSE 'EXCELLENT'
    END AS credit_score_band,

    CASE
        WHEN fr.amount > da.balance THEN TRUE
        ELSE FALSE
    END AS insufficient_balance_risk_flag,

    CURRENT_TIMESTAMP AS analytics_generated_at

FROM fraud_results fr
LEFT JOIN customer_current dc ON fr.customer_id = dc.customer_id
LEFT JOIN account_current da    ON fr.account_id = da.account_id
LEFT JOIN device_current dd    ON fr.device_id = dd.device_id
LEFT JOIN location_current dl  ON fr.location_id = dl.location_id;

--Table for Dashboards
CREATE TABLE IF NOT EXISTS curated.fraud_transaction_analytics AS 
SELECT * FROM curated.vw_fraud_transaction_analytics;