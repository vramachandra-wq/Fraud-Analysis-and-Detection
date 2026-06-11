

-- Create staging schema
CREATE SCHEMA IF NOT EXISTS staging;


-- 1. STG_CUSTOMERS
CREATE TABLE IF NOT EXISTS staging.stg_customers (
    customer_id         VARCHAR(50) PRIMARY KEY,
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
    occupation          VARCHAR(100)
);

-- 2. STG_ACCOUNTS
CREATE TABLE IF NOT EXISTS staging.stg_accounts (
    account_id              VARCHAR(50) PRIMARY KEY,
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
    updated_at              TIMESTAMP
);

-- 3. STG_DEVICES
CREATE TABLE IF NOT EXISTS staging.stg_devices (
    device_id           VARCHAR(50) PRIMARY KEY,
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
    created_at          TIMESTAMP
);


-- 4. STG_LOCATIONS
CREATE TABLE IF NOT EXISTS staging.stg_locations (
    location_id         VARCHAR(50) PRIMARY KEY,
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
    created_at          TIMESTAMP
);

-- 5. STG_TRANSACTIONS
CREATE TABLE IF NOT EXISTS staging.stg_transactions (
    transaction_id      VARCHAR(50) PRIMARY KEY,
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
    notes               TEXT
);