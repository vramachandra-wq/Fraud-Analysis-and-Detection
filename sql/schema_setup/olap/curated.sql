
--curated 2

CREATE SCHEMA IF NOT EXISTS curated;

-- 1. DIM_CUSTOMER — SCD Type 2
CREATE TABLE IF NOT EXISTS curated.dim_customer (
    dim_customer_sk     BIGSERIAL PRIMARY KEY,       -- surrogate key
    customer_id         VARCHAR(50),                 -- business key (no PK)
    full_name           VARCHAR(200),
    email               VARCHAR(150),
    phone               VARCHAR(20),
    date_of_birth       DATE,
    gender              VARCHAR(10),
    nationality         VARCHAR(50),
    city                VARCHAR(100),
    state               VARCHAR(100),
    country             VARCHAR(50),
    is_active           BOOLEAN,
    credit_score        INTEGER,
    annual_income       NUMERIC(15,2),
    occupation          VARCHAR(100),
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    valid_from          TIMESTAMP,
    valid_to            TIMESTAMP,                   -- NULL means current
    is_current          BOOLEAN DEFAULT true,
    dwh_created_at      TIMESTAMP DEFAULT NOW(),
    dwh_updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_customer_bk ON curated.dim_customer(customer_id);
CREATE INDEX IF NOT EXISTS idx_dim_customer_current ON curated.dim_customer(customer_id, is_current);

-- 2. DIM_ACCOUNT — SCD Type 2
CREATE TABLE IF NOT EXISTS curated.dim_account (
    dim_account_sk      BIGSERIAL PRIMARY KEY,
    account_id          VARCHAR(50),
    customer_id         VARCHAR(50),
    account_number      VARCHAR(50),
    account_type        VARCHAR(50),
    account_status      VARCHAR(20),
    bank_name           VARCHAR(100),
    currency            VARCHAR(10),
    balance             NUMERIC(15,2),
    credit_limit        NUMERIC(15,2),
    opening_date        DATE,
    closing_date        DATE,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    valid_from          TIMESTAMP,
    valid_to            TIMESTAMP,
    is_current          BOOLEAN DEFAULT true,
    dwh_created_at      TIMESTAMP DEFAULT NOW(),
    dwh_updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_account_bk ON curated.dim_account(account_id);
CREATE INDEX IF NOT EXISTS idx_dim_account_current ON curated.dim_account(account_id, is_current);

-- 3. DIM_DEVICE — SCD Type 2
CREATE TABLE IF NOT EXISTS curated.dim_device (
    dim_device_sk       BIGSERIAL PRIMARY KEY,
    device_id           VARCHAR(50),
    customer_id         VARCHAR(50),
    device_type         VARCHAR(50),
    operating_system    VARCHAR(50),
    browser             VARCHAR(50),
    ip_address          VARCHAR(50),
    is_trusted          BOOLEAN,
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP,
    created_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    valid_from          TIMESTAMP,
    valid_to            TIMESTAMP,
    is_current          BOOLEAN DEFAULT true,
    dwh_created_at      TIMESTAMP DEFAULT NOW(),
    dwh_updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_device_bk ON curated.dim_device(device_id);
CREATE INDEX IF NOT EXISTS idx_dim_device_current ON curated.dim_device(device_id, is_current);

-- 4. DIM_LOCATION — SCD Type 2

CREATE TABLE IF NOT EXISTS curated.dim_location (
    dim_location_sk     BIGSERIAL PRIMARY KEY,
    location_id         VARCHAR(50),
    merchant_name       VARCHAR(200),
    merchant_category   VARCHAR(100),
    city                VARCHAR(100),
    state               VARCHAR(100),
    country             VARCHAR(50),
    latitude            NUMERIC(10,6),
    longitude           NUMERIC(10,6),
    is_high_risk_area   BOOLEAN,
    created_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    valid_from          TIMESTAMP,
    valid_to            TIMESTAMP,
    is_current          BOOLEAN DEFAULT true,
    dwh_created_at      TIMESTAMP DEFAULT NOW(),
    dwh_updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_location_bk ON curated.dim_location(location_id);
CREATE INDEX IF NOT EXISTS idx_dim_location_current ON curated.dim_location(location_id, is_current);

-- 5. FACT_TRANSACTIONS
CREATE TABLE IF NOT EXISTS curated.fact_transactions (
    transaction_id      VARCHAR(50) PRIMARY KEY,
    account_id          VARCHAR(50),
    customer_id         VARCHAR(50),
    device_id           VARCHAR(50),
    location_id         VARCHAR(50),
    transaction_type    VARCHAR(50),
    channel             VARCHAR(50),
    amount              NUMERIC(15,2),
    currency            VARCHAR(10),
    transaction_status  VARCHAR(20),
    is_fraud            BOOLEAN,
    fraud_reason        VARCHAR(200),
    transaction_date    DATE,
    transaction_time    TIME,
    processing_time_ms  INTEGER,
    reference_number    VARCHAR(100),
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    dwh_created_at      TIMESTAMP DEFAULT NOW(),
    dwh_updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_transactions_account ON curated.fact_transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_customer ON curated.fact_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_device ON curated.fact_transactions(device_id);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_location ON curated.fact_transactions(location_id);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_fraud ON curated.fact_transactions(is_fraud);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_date ON curated.fact_transactions(transaction_date);

-- 6. FACT_FRAUD_ALERTS
CREATE TABLE IF NOT EXISTS curated.fact_fraud_alerts (
    alert_id            SERIAL PRIMARY KEY,
    transaction_id      VARCHAR(50),
    customer_id         VARCHAR(50),
    account_id          VARCHAR(50),
    fraud_reason        VARCHAR(200),
    amount              NUMERIC(15,2),
    transaction_date    DATE,
    alert_created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fraud_alerts_transaction ON curated.fact_fraud_alerts(transaction_id);
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_customer ON curated.fact_fraud_alerts(customer_id);
