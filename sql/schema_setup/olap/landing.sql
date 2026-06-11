-- OLAP CDC LANDING LAYER 


-- Landing schema
CREATE SCHEMA IF NOT EXISTS landing;


-- 1. CUSTOMERS
CREATE TABLE IF NOT EXISTS landing.customers (
    event_id            BIGSERIAL,              
    customer_id         VARCHAR(50),            
    first_name          VARCHAR(100),
    last_name           VARCHAR(100),
    email               VARCHAR(150),
    phone               VARCHAR(20),
    date_of_birth       DATE,
    gender              VARCHAR(10),
    nationality         VARCHAR(50),
    address_line1       VARCHAR(200),
    address_line2       VARCHAR(200),
    city                VARCHAR(100),
    state               VARCHAR(100),
    zip_code            VARCHAR(20),
    country             VARCHAR(50),
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    is_active           BOOLEAN,
    credit_score        INTEGER,
    annual_income       NUMERIC(15,2),
    occupation          VARCHAR(100),
    cdc_operation       VARCHAR(10),
    cdc_timestamp       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_landing_customers_id ON landing.customers(customer_id);
CREATE INDEX idx_landing_customers_ts ON landing.customers(cdc_timestamp);
CREATE INDEX idx_landing_customers_op ON landing.customers(cdc_operation);

-- 2. ACCOUNTS
CREATE TABLE IF NOT EXISTS landing.accounts (
    event_id                BIGSERIAL,
    account_id              VARCHAR(50),
    customer_id             VARCHAR(50),
    account_number          VARCHAR(50),
    account_type            VARCHAR(50),
    account_status          VARCHAR(20),
    bank_name               VARCHAR(100),
    routing_number          VARCHAR(50),
    currency                VARCHAR(10),
    balance                 NUMERIC(15,2),
    credit_limit            NUMERIC(15,2),
    opening_date            DATE,
    closing_date            DATE,
    last_transaction_date   DATE,
    created_at              TIMESTAMP,
    updated_at              TIMESTAMP,
    cdc_operation           VARCHAR(10),
    cdc_timestamp           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_landing_accounts_id ON landing.accounts(account_id);
CREATE INDEX idx_landing_accounts_ts ON landing.accounts(cdc_timestamp);
CREATE INDEX idx_landing_accounts_op ON landing.accounts(cdc_operation);

-- 3. DEVICES
CREATE TABLE IF NOT EXISTS landing.devices (
    event_id            BIGSERIAL,
    device_id           VARCHAR(50),
    customer_id         VARCHAR(50),
    device_type         VARCHAR(50),
    device_fingerprint  VARCHAR(200),
    operating_system    VARCHAR(50),
    os_version          VARCHAR(50),
    browser             VARCHAR(50),
    browser_version     VARCHAR(50),
    ip_address          VARCHAR(50),
    mac_address         VARCHAR(50),
    is_trusted          BOOLEAN,
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP,
    created_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    cdc_timestamp       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_landing_devices_id ON landing.devices(device_id);
CREATE INDEX idx_landing_devices_ts ON landing.devices(cdc_timestamp);
CREATE INDEX idx_landing_devices_op ON landing.devices(cdc_operation);

-- 4. LOCATIONS
CREATE TABLE IF NOT EXISTS landing.locations (
    event_id            BIGSERIAL,
    location_id         VARCHAR(50),
    merchant_name       VARCHAR(200),
    merchant_category   VARCHAR(100),
    address_line1       VARCHAR(200),
    city                VARCHAR(100),
    state               VARCHAR(100),
    zip_code            VARCHAR(20),
    country             VARCHAR(50),
    latitude            NUMERIC(10,6),
    longitude           NUMERIC(10,6),
    is_high_risk_area   BOOLEAN,
    created_at          TIMESTAMP,
    cdc_operation       VARCHAR(10),
    cdc_timestamp       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_landing_locations_id ON landing.locations(location_id);
CREATE INDEX idx_landing_locations_ts ON landing.locations(cdc_timestamp);
CREATE INDEX idx_landing_locations_op ON landing.locations(cdc_operation);

-- 5. TRANSACTIONS
CREATE TABLE IF NOT EXISTS landing.transactions (
    event_id            BIGSERIAL,
    transaction_id      VARCHAR(50),
    account_id          VARCHAR(50),
    device_id           VARCHAR(50),
    location_id         VARCHAR(50),
    transaction_type    VARCHAR(50),
    channel             VARCHAR(50),
    amount              NUMERIC(15,2),
    currency            VARCHAR(10),
    transaction_status  VARCHAR(20),
    merchant_name       VARCHAR(200),
    merchant_category   VARCHAR(100),
    is_fraud            BOOLEAN,
    fraud_reason        VARCHAR(200),
    transaction_date    DATE,
    transaction_time    TIME,
    processing_time_ms  INTEGER,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    reference_number    VARCHAR(100),
    notes               TEXT,
    cdc_operation       VARCHAR(10),
    cdc_timestamp       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_landing_transactions_id ON landing.transactions(transaction_id);
CREATE INDEX idx_landing_transactions_ts ON landing.transactions(cdc_timestamp);
CREATE INDEX idx_landing_transactions_fraud ON landing.transactions(is_fraud);
CREATE INDEX idx_landing_transactions_op ON landing.transactions(cdc_operation);