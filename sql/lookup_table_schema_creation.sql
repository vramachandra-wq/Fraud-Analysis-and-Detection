--Lookup Table SCHEMA
CREATE SCHEMA IF NOT EXISTS lookup;

CREATE TABLE IF NOT EXISTS lookup.valid_accounts(
	account_id VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS lookup.blacklist_accounts(
	account_id VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS lookup.vip_accounts(
	account_id VARCHAR(100),
	amount_per_transaction_limit NUMERIC,
	transactions_limit INT
);