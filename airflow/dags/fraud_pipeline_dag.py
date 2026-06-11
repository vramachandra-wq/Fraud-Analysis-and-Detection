

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import logging
import psycopg2

logger = logging.getLogger(__name__)

default_args = {
    "owner": "fraud_pipeline",
    "depends_on_past": False,
    "start_date": datetime(2026, 3, 25),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry": False
}

dag = DAG(
    dag_id="fraud_pipeline_dag",
    default_args=default_args,
    description="Idempotent Incremental SCD Type 2 Pipeline",
    schedule_interval=timedelta(hours=1),
    catchup=False,
    tags=["fraud", "pipeline", "curated", "scd2"]
)

OLAP_CONN = {
    "host": "olap_db",
    "port": 5432,
    "dbname": "fraud_olap",
    "user": "postgres",
    "password": "Master#123"
}


def get_conn():
    return psycopg2.connect(**OLAP_CONN)


def log_to_db(service, log_level, event_type, table_name,
              message, error_details=None, rows_affected=0):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO logging.pipeline_logs
                (service, log_level, event_type, table_name, message,
                 error_details, rows_affected, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (service, log_level, event_type, table_name,
                  message, error_details, rows_affected, datetime.utcnow()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to write to logging table: {e}")


def get_last_run_timestamp():
    try:
        return Variable.get("fraud_pipeline_last_run")
    except Exception:
        return "1970-01-01 00:00:00"


def set_last_run_timestamp(ts):
    Variable.set("fraud_pipeline_last_run", str(ts))

# TASK 1 — CHECK LANDING DATA

def check_landing_data(**context):
    conn = get_conn()
    last_run = get_last_run_timestamp()

    # Capture run_start NOW — we process data between last_run and run_start
    # This prevents race condition where new data arrives during processing
    run_start = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")

    logger.info(f"Processing window: {last_run} -> {run_start}")

    counts = {}
    tables = ["customers", "accounts", "transactions", "devices", "locations"]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"""
                SELECT COUNT(*) FROM landing.{table}
                WHERE cdc_timestamp > '{last_run}'
                AND cdc_timestamp <= '{run_start}'
            """)
            counts[table] = cur.fetchone()[0]

    logger.info(f"New records in window: {counts}")
    log_to_db("airflow", "INFO", "CHECK_LANDING", "landing",
              f"Window: {last_run} -> {run_start} | Records: {counts}",
              rows_affected=counts.get("transactions", 0))
    conn.close()

    # Push both last_run and run_start for downstream tasks
    context['ti'].xcom_push(key='last_run', value=last_run)
    context['ti'].xcom_push(key='run_start', value=run_start)
    context['ti'].xcom_push(key='new_record_counts', value=counts)


# -----------------------------------------------------------------------------
# TASK 2 — SODA DQ CHECK 1 (Landing Layer)
# -----------------------------------------------------------------------------
def soda_dq_check_1(**context):
    from soda.scan import Scan

    logger.info("Running Soda DQ Check 1 on landing tables...")
    scan = Scan()
    scan.set_data_source_name("fraud_olap")
    scan.add_configuration_yaml_file("/opt/airflow/dags/soda_config.yml")

    scan.add_sodacl_yaml_str("""
checks for landing.customers:
  - missing_count(customer_id) = 0:
      name: "No null customer IDs"
  - missing_count(first_name):
      warn: when > 50000
      fail: when > 180000
      name: "First name nulls acceptable"
  - missing_count(last_name):
      warn: when > 50000
      fail: when > 180000
      name: "Last name nulls acceptable"
  - missing_count(email):
      warn: when > 50000
      fail: when > 180000
      name: "Email nulls acceptable"
  - missing_count(phone):
      warn: when > 50000
      fail: when > 180000
      name: "Phone nulls acceptable"
  - missing_count(gender):
      warn: when > 50000
      fail: when > 180000
      name: "Gender nulls acceptable"
  - missing_count(nationality):
      warn: when > 50000
      fail: when > 180000
      name: "Nationality nulls acceptable"
  - missing_count(city):
      warn: when > 50000
      fail: when > 180000
      name: "City nulls acceptable"
  - missing_count(country):
      warn: when > 50000
      fail: when > 180000
      name: "Country nulls acceptable"
  - missing_count(credit_score):
      warn: when > 50000
      fail: when > 180000
      name: "Credit score nulls acceptable"
  - missing_count(annual_income):
      warn: when > 50000
      fail: when > 180000
      name: "Annual income nulls acceptable"
  - missing_count(is_active):
      warn: when > 10000
      fail: when > 180000
      name: "Is active nulls acceptable"

checks for landing.accounts:
  - missing_count(account_id) = 0:
      name: "No null account IDs"
  - missing_count(customer_id) = 0:
      name: "No null customer IDs in accounts"
  - missing_count(account_type):
      warn: when > 10000
      fail: when > 200000
      name: "Account type nulls acceptable"
  - missing_count(account_status):
      warn: when > 10000
      fail: when > 200000
      name: "Account status nulls acceptable"
  - missing_count(balance):
      warn: when > 10000
      fail: when > 200000
      name: "Balance nulls acceptable"
  - missing_count(currency):
      warn: when > 10000
      fail: when > 200000
      name: "Currency nulls acceptable"

checks for landing.transactions:
  - missing_count(transaction_id) = 0:
      name: "No null transaction IDs"
  - missing_count(account_id) = 0:
      name: "No null account IDs in transactions"
  - missing_count(amount) = 0:
      name: "No null amounts"
  - min(amount) >= 0:
      name: "No negative amounts"
  - missing_count(transaction_date) = 0:
      name: "No null transaction dates"
  - missing_count(is_fraud) = 0:
      name: "No null fraud flags"
  - missing_count(transaction_type):
      warn: when > 10000
      fail: when > 2500000
      name: "Transaction type nulls acceptable"
  - missing_count(currency):
      warn: when > 10000
      fail: when > 2500000
      name: "Currency nulls acceptable"
  - missing_count(transaction_status):
      warn: when > 10000
      fail: when > 2500000
      name: "Transaction status nulls acceptable"
  - missing_count(device_id):
      warn: when > 100000
      fail: when > 2500000
      name: "Device ID nulls acceptable"
  - missing_count(location_id):
      warn: when > 100000
      fail: when > 2500000
      name: "Location ID nulls acceptable"

checks for landing.devices:
  - missing_count(device_id) = 0:
      name: "No null device IDs"
  - missing_count(customer_id) = 0:
      name: "No null customer IDs in devices"
  - missing_count(device_type):
      warn: when > 10000
      fail: when > 250000
      name: "Device type nulls acceptable"
  - missing_count(operating_system):
      warn: when > 10000
      fail: when > 250000
      name: "OS nulls acceptable"
  - missing_count(ip_address):
      warn: when > 10000
      fail: when > 250000
      name: "IP address nulls acceptable"
  - missing_count(is_trusted):
      warn: when > 10000
      fail: when > 250000
      name: "Is trusted nulls acceptable"

checks for landing.locations:
  - missing_count(location_id) = 0:
      name: "No null location IDs"
  - missing_count(merchant_name):
      warn: when > 5000
      fail: when > 100000
      name: "Merchant name nulls acceptable"
  - missing_count(merchant_category):
      warn: when > 5000
      fail: when > 100000
      name: "Merchant category nulls acceptable"
  - missing_count(city):
      warn: when > 5000
      fail: when > 100000
      name: "Location city nulls acceptable"
  - missing_count(country):
      warn: when > 5000
      fail: when > 100000
      name: "Location country nulls acceptable"
  - missing_count(is_high_risk_area):
      warn: when > 5000
      fail: when > 100000
      name: "High risk area flag nulls acceptable"
""")

    scan.execute()

    if scan.has_check_fails():
        failed_checks = [str(c) for c in scan.get_checks_fail()]
        error_msg = f"Soda DQ Check 1 FAILED: {failed_checks}"
        logger.error(error_msg)
        log_to_db("airflow", "ERROR", "SODA_DQ_CHECK_1", "landing",
                  error_msg, error_details=str(failed_checks))
        raise Exception(error_msg)
    else:
        logger.info("Soda DQ Check 1 PASSED")
        log_to_db("airflow", "INFO", "SODA_DQ_CHECK_1", "landing",
                  "DQ Check 1 passed")


def apply_scd2(conn, staging_query, target_table, business_key,
               compare_columns, insert_columns, insert_select):
    """
    Generic SCD2 loader.
    staging_query: SQL that returns deduplicated staging data
    target_table: curated table name
    business_key: column name of business key
    compare_columns: list of columns to detect changes
    insert_columns: column list for INSERT
    insert_select: SELECT portion for INSERT
    """
    with conn.cursor() as cur:

        # Step 1 — Create temp staging table with latest per business key
        cur.execute(f"CREATE TEMP TABLE tmp_scd2_staging AS {staging_query}")

        # Step 2 — Fix any data integrity issues first
        # Ensure only one is_current=true per business key (safety net)
        cur.execute(f"""
            UPDATE {target_table} d1
            SET is_current = false,
                valid_to = NOW(),
                dwh_updated_at = NOW()
            WHERE d1.is_current = true
            AND EXISTS (
                SELECT 1 FROM {target_table} d2
                WHERE d2.{business_key} = d1.{business_key}
                AND d2.is_current = true
                AND d2.dwh_created_at > d1.dwh_created_at
            )
        """)

        # Step 3 — Expire current rows where values changed
        change_conditions = " OR\n                ".join([
            f"d.{col} IS DISTINCT FROM s.{col}" for col in compare_columns
        ])
        cur.execute(f"""
            UPDATE {target_table} d
            SET
                valid_to = s.cdc_timestamp,
                is_current = false,
                dwh_updated_at = NOW()
            FROM tmp_scd2_staging s
            WHERE d.{business_key} = s.{business_key}
            AND d.is_current = true
            AND (
                {change_conditions}
            )
        """)
        expired = cur.rowcount

        # Step 4 — Insert new versions ONLY where no identical current row exists
        # This makes the operation idempotent
        all_compare = " AND\n                ".join([
            f"d.{col} IS NOT DISTINCT FROM s.{col}" for col in compare_columns
        ])
        cur.execute(f"""
            INSERT INTO {target_table} ({insert_columns})
            SELECT {insert_select}
            FROM tmp_scd2_staging s
            WHERE NOT EXISTS (
                SELECT 1 FROM {target_table} d
                WHERE d.{business_key} = s.{business_key}
                AND d.is_current = true
                AND {all_compare}
            )
        """)
        inserted = cur.rowcount

        # Step 5 — Cleanup
        cur.execute("DROP TABLE IF EXISTS tmp_scd2_staging")

    return expired, inserted


# -----------------------------------------------------------------------------
# TASK 3 — LOAD DIM_CUSTOMER (SCD Type 2)
# -----------------------------------------------------------------------------
def load_dim_customer(**context):
    conn = get_conn()
    last_run = context['ti'].xcom_pull(key='last_run', task_ids='check_landing_data')
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    logger.info(f"Loading dim_customer SCD2 | window: {last_run} -> {run_start}")

    staging_query = f"""
        SELECT DISTINCT ON (customer_id)
            customer_id,
            TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) AS full_name,
            LOWER(COALESCE(email, 'unknown@unknown.com')) AS email,
            COALESCE(phone, 'N/A') AS phone,
            date_of_birth,
            COALESCE(UPPER(gender), 'UNKNOWN') AS gender,
            COALESCE(nationality, 'UNKNOWN') AS nationality,
            COALESCE(city, 'UNKNOWN') AS city,
            COALESCE(state, 'UNKNOWN') AS state,
            COALESCE(UPPER(country), 'UNKNOWN') AS country,
            COALESCE(is_active, false) AS is_active,
            credit_score,
            annual_income,
            COALESCE(occupation, 'UNKNOWN') AS occupation,
            COALESCE(created_at, cdc_timestamp) AS created_at,
            COALESCE(updated_at, cdc_timestamp) AS updated_at,
            cdc_operation,
            cdc_timestamp
        FROM landing.customers
        WHERE cdc_timestamp > '{last_run}'
        AND cdc_timestamp <= '{run_start}'
        ORDER BY customer_id, cdc_timestamp DESC
    """

    compare_columns = [
        "full_name", "email", "phone", "date_of_birth", "gender",
        "nationality", "city", "state", "country", "is_active",
        "credit_score", "annual_income", "occupation"
    ]

    insert_columns = """
        customer_id, full_name, email, phone, date_of_birth,
        gender, nationality, city, state, country,
        is_active, credit_score, annual_income, occupation,
        created_at, updated_at, cdc_operation,
        valid_from, valid_to, is_current,
        dwh_created_at, dwh_updated_at
    """

    insert_select = """
        s.customer_id, s.full_name, s.email, s.phone, s.date_of_birth,
        s.gender, s.nationality, s.city, s.state, s.country,
        s.is_active, s.credit_score, s.annual_income, s.occupation,
        s.created_at, s.updated_at, s.cdc_operation,
        s.cdc_timestamp AS valid_from,
        NULL AS valid_to,
        true AS is_current,
        NOW(), NOW()
    """

    expired, inserted = apply_scd2(
        conn, staging_query, "curated.dim_customer",
        "customer_id", compare_columns, insert_columns, insert_select
    )

    conn.commit()
    logger.info(f"dim_customer SCD2: {expired} expired, {inserted} inserted")
    log_to_db("airflow", "INFO", "LOAD_DIM_SCD2", "curated.dim_customer",
              f"SCD2: {expired} expired, {inserted} new versions",
              rows_affected=inserted)
    conn.close()


# -----------------------------------------------------------------------------
# TASK 4 — LOAD DIM_ACCOUNT (SCD Type 2)
# -----------------------------------------------------------------------------
def load_dim_account(**context):
    conn = get_conn()
    last_run = context['ti'].xcom_pull(key='last_run', task_ids='check_landing_data')
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    logger.info(f"Loading dim_account SCD2 | window: {last_run} -> {run_start}")

    staging_query = f"""
        SELECT DISTINCT ON (account_id)
            account_id,
            customer_id,
            COALESCE(account_number, 'UNKNOWN') AS account_number,
            COALESCE(UPPER(account_type), 'UNKNOWN') AS account_type,
            COALESCE(UPPER(account_status), 'UNKNOWN') AS account_status,
            COALESCE(bank_name, 'UNKNOWN') AS bank_name,
            COALESCE(UPPER(currency), 'USD') AS currency,
            balance,
            credit_limit,
            opening_date,
            closing_date,
            COALESCE(created_at, cdc_timestamp) AS created_at,
            COALESCE(updated_at, cdc_timestamp) AS updated_at,
            cdc_operation,
            cdc_timestamp
        FROM landing.accounts
        WHERE cdc_timestamp > '{last_run}'
        AND cdc_timestamp <= '{run_start}'
        ORDER BY account_id, cdc_timestamp DESC
    """

    compare_columns = [
        "customer_id", "account_type", "account_status", "bank_name",
        "currency", "balance", "credit_limit", "closing_date"
    ]

    insert_columns = """
        account_id, customer_id, account_number, account_type,
        account_status, bank_name, currency, balance, credit_limit,
        opening_date, closing_date, created_at, updated_at,
        cdc_operation, valid_from, valid_to, is_current,
        dwh_created_at, dwh_updated_at
    """

    insert_select = """
        s.account_id, s.customer_id, s.account_number, s.account_type,
        s.account_status, s.bank_name, s.currency, s.balance, s.credit_limit,
        s.opening_date, s.closing_date, s.created_at, s.updated_at,
        s.cdc_operation, s.cdc_timestamp, NULL, true, NOW(), NOW()
    """

    expired, inserted = apply_scd2(
        conn, staging_query, "curated.dim_account",
        "account_id", compare_columns, insert_columns, insert_select
    )

    conn.commit()
    logger.info(f"dim_account SCD2: {expired} expired, {inserted} inserted")
    log_to_db("airflow", "INFO", "LOAD_DIM_SCD2", "curated.dim_account",
              f"SCD2: {expired} expired, {inserted} new versions",
              rows_affected=inserted)
    conn.close()


# -----------------------------------------------------------------------------
# TASK 5 — LOAD DIM_DEVICE (SCD Type 2)
# -----------------------------------------------------------------------------
def load_dim_device(**context):
    conn = get_conn()
    last_run = context['ti'].xcom_pull(key='last_run', task_ids='check_landing_data')
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    logger.info(f"Loading dim_device SCD2 | window: {last_run} -> {run_start}")

    staging_query = f"""
        SELECT DISTINCT ON (device_id)
            device_id,
            customer_id,
            COALESCE(UPPER(device_type), 'UNKNOWN') AS device_type,
            COALESCE(UPPER(operating_system), 'UNKNOWN') AS operating_system,
            COALESCE(browser, 'UNKNOWN') AS browser,
            COALESCE(ip_address, '0.0.0.0') AS ip_address,
            COALESCE(is_trusted, false) AS is_trusted,
            first_seen_at,
            last_seen_at,
            COALESCE(created_at, cdc_timestamp) AS created_at,
            cdc_operation,
            cdc_timestamp
        FROM landing.devices
        WHERE cdc_timestamp > '{last_run}'
        AND cdc_timestamp <= '{run_start}'
        ORDER BY device_id, cdc_timestamp DESC
    """

    compare_columns = [
        "device_type", "operating_system", "browser",
        "ip_address", "is_trusted", "last_seen_at"
    ]

    insert_columns = """
        device_id, customer_id, device_type, operating_system,
        browser, ip_address, is_trusted, first_seen_at,
        last_seen_at, created_at, cdc_operation,
        valid_from, valid_to, is_current,
        dwh_created_at, dwh_updated_at
    """

    insert_select = """
        s.device_id, s.customer_id, s.device_type, s.operating_system,
        s.browser, s.ip_address, s.is_trusted, s.first_seen_at,
        s.last_seen_at, s.created_at, s.cdc_operation,
        s.cdc_timestamp, NULL, true, NOW(), NOW()
    """

    expired, inserted = apply_scd2(
        conn, staging_query, "curated.dim_device",
        "device_id", compare_columns, insert_columns, insert_select
    )

    conn.commit()
    logger.info(f"dim_device SCD2: {expired} expired, {inserted} inserted")
    log_to_db("airflow", "INFO", "LOAD_DIM_SCD2", "curated.dim_device",
              f"SCD2: {expired} expired, {inserted} new versions",
              rows_affected=inserted)
    conn.close()


# -----------------------------------------------------------------------------
# TASK 6 — LOAD DIM_LOCATION (SCD Type 2)
# -----------------------------------------------------------------------------
def load_dim_location(**context):
    conn = get_conn()
    last_run = context['ti'].xcom_pull(key='last_run', task_ids='check_landing_data')
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    logger.info(f"Loading dim_location SCD2 | window: {last_run} -> {run_start}")

    staging_query = f"""
        SELECT DISTINCT ON (location_id)
            location_id,
            COALESCE(merchant_name, 'UNKNOWN') AS merchant_name,
            COALESCE(UPPER(merchant_category), 'UNKNOWN') AS merchant_category,
            COALESCE(city, 'UNKNOWN') AS city,
            state,
            COALESCE(UPPER(country), 'UNKNOWN') AS country,
            latitude,
            longitude,
            COALESCE(is_high_risk_area, false) AS is_high_risk_area,
            COALESCE(created_at, cdc_timestamp) AS created_at,
            cdc_operation,
            cdc_timestamp
        FROM landing.locations
        WHERE cdc_timestamp > '{last_run}'
        AND cdc_timestamp <= '{run_start}'
        ORDER BY location_id, cdc_timestamp DESC
    """

    compare_columns = [
        "merchant_name", "merchant_category", "city", "state",
        "country", "latitude", "longitude", "is_high_risk_area"
    ]

    insert_columns = """
        location_id, merchant_name, merchant_category,
        city, state, country, latitude, longitude,
        is_high_risk_area, created_at, cdc_operation,
        valid_from, valid_to, is_current,
        dwh_created_at, dwh_updated_at
    """

    insert_select = """
        s.location_id, s.merchant_name, s.merchant_category,
        s.city, s.state, s.country, s.latitude, s.longitude,
        s.is_high_risk_area, s.created_at, s.cdc_operation,
        s.cdc_timestamp, NULL, true, NOW(), NOW()
    """

    expired, inserted = apply_scd2(
        conn, staging_query, "curated.dim_location",
        "location_id", compare_columns, insert_columns, insert_select
    )

    conn.commit()
    logger.info(f"dim_location SCD2: {expired} expired, {inserted} inserted")
    log_to_db("airflow", "INFO", "LOAD_DIM_SCD2", "curated.dim_location",
              f"SCD2: {expired} expired, {inserted} new versions",
              rows_affected=inserted)
    conn.close()


# -----------------------------------------------------------------------------
# TASK 7 — LOAD FACT_TRANSACTIONS
# -----------------------------------------------------------------------------
def load_fact_transactions(**context):
    conn = get_conn()
    last_run = context['ti'].xcom_pull(key='last_run', task_ids='check_landing_data')
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    logger.info(f"Loading fact_transactions | window: {last_run} -> {run_start}")

    with conn.cursor() as cur:

        # Deduplicate: keep latest CDC event per transaction_id in window
        cur.execute(f"""
            CREATE TEMP TABLE tmp_transactions_latest AS
            SELECT DISTINCT ON (transaction_id)
                transaction_id,
                account_id,
                device_id,
                location_id,
                transaction_type,
                channel,
                amount,
                currency,
                transaction_status,
                is_fraud,
                fraud_reason,
                transaction_date,
                transaction_time,
                processing_time_ms,
                reference_number,
                created_at,
                updated_at,
                cdc_operation,
                cdc_timestamp
            FROM landing.transactions
            WHERE cdc_timestamp > '{last_run}'
            AND cdc_timestamp <= '{run_start}'
            ORDER BY transaction_id, cdc_timestamp DESC
        """)

        # Insert with ON CONFLICT UPDATE — idempotent
        cur.execute("""
            INSERT INTO curated.fact_transactions (
                transaction_id, account_id, customer_id, device_id, location_id,
                transaction_type, channel, amount, currency, transaction_status,
                is_fraud, fraud_reason, transaction_date, transaction_time,
                processing_time_ms, reference_number, created_at, updated_at,
                cdc_operation, dwh_created_at, dwh_updated_at
            )
            SELECT
                t.transaction_id,
                t.account_id,
                COALESCE(da.customer_id, la.customer_id, 'UNKNOWN') AS customer_id,
                t.device_id,
                t.location_id,
                COALESCE(UPPER(t.transaction_type), 'UNKNOWN') AS transaction_type,
                COALESCE(UPPER(t.channel), 'UNKNOWN') AS channel,
                COALESCE(t.amount, 0.00) AS amount,
                COALESCE(UPPER(t.currency), 'USD') AS currency,
                COALESCE(UPPER(t.transaction_status), 'UNKNOWN') AS transaction_status,
                COALESCE(t.is_fraud, false) AS is_fraud,
                t.fraud_reason,
                t.transaction_date,
                t.transaction_time,
                t.processing_time_ms,
                COALESCE(t.reference_number, 'UNKNOWN') AS reference_number,
                COALESCE(t.created_at, t.cdc_timestamp) AS created_at,
                COALESCE(t.updated_at, t.cdc_timestamp) AS updated_at,
                t.cdc_operation,
                NOW(),
                NOW()
            FROM tmp_transactions_latest t
            LEFT JOIN curated.dim_account da
                ON t.account_id = da.account_id
                AND da.is_current = true
            LEFT JOIN landing.accounts la
                ON t.account_id = la.account_id
            ON CONFLICT (transaction_id) DO UPDATE SET
                transaction_status = EXCLUDED.transaction_status,
                is_fraud = EXCLUDED.is_fraud,
                fraud_reason = EXCLUDED.fraud_reason,
                amount = EXCLUDED.amount,
                customer_id = EXCLUDED.customer_id,
                device_id = EXCLUDED.device_id,
                location_id = EXCLUDED.location_id,
                updated_at = EXCLUDED.updated_at,
                cdc_operation = EXCLUDED.cdc_operation,
                dwh_updated_at = NOW()
        """)
        rows = cur.rowcount

        cur.execute("DROP TABLE IF EXISTS tmp_transactions_latest")

    conn.commit()
    logger.info(f"fact_transactions loaded: {rows} rows")
    log_to_db("airflow", "INFO", "LOAD_FACT", "curated.fact_transactions",
              f"Loaded {rows} rows", rows_affected=rows)
    conn.close()


# -----------------------------------------------------------------------------
# TASK 8 — LOAD FACT_FRAUD_ALERTS
# -----------------------------------------------------------------------------
def load_fact_fraud_alerts(**context):
    conn = get_conn()
    last_run = context['ti'].xcom_pull(key='last_run', task_ids='check_landing_data')
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    logger.info(f"Loading fact_fraud_alerts | window: {last_run} -> {run_start}")

    with conn.cursor() as cur:
        cur.execute(f"""
            INSERT INTO curated.fact_fraud_alerts (
                transaction_id, customer_id, account_id,
                fraud_reason, amount, transaction_date, alert_created_at
            )
            SELECT
                ft.transaction_id,
                ft.customer_id,
                ft.account_id,
                ft.fraud_reason,
                ft.amount,
                ft.transaction_date,
                NOW()
            FROM curated.fact_transactions ft
            WHERE ft.is_fraud = true
            AND ft.dwh_updated_at > '{last_run}'
            AND ft.dwh_updated_at <= '{run_start}'
            AND NOT EXISTS (
                SELECT 1 FROM curated.fact_fraud_alerts fa
                WHERE fa.transaction_id = ft.transaction_id
            )
        """)
        rows = cur.rowcount

    conn.commit()
    logger.info(f"fact_fraud_alerts loaded: {rows} fraud alerts")
    log_to_db("airflow", "INFO", "LOAD_FACT", "curated.fact_fraud_alerts",
              f"Loaded {rows} fraud alerts", rows_affected=rows)
    conn.close()


# -----------------------------------------------------------------------------
# TASK 9 — SODA DQ CHECK 2 (Curated Layer)
# -----------------------------------------------------------------------------
def soda_dq_check_2(**context):
    from soda.scan import Scan

    logger.info("Running Soda DQ Check 2 on curated tables...")
    scan = Scan()
    scan.set_data_source_name("fraud_olap")
    scan.add_configuration_yaml_file("/opt/airflow/dags/soda_config.yml")

    scan.add_sodacl_yaml_str("""
checks for curated.dim_customer:
  - missing_count(customer_id) = 0:
      name: "No null customer IDs"
  - missing_count(full_name) = 0:
      name: "No null full names"
  - missing_count(email) = 0:
      name: "No null emails"
  - missing_count(country) = 0:
      name: "No null countries"
  - missing_count(valid_from) = 0:
      name: "No null valid_from in dim_customer"
  - missing_count(is_current) = 0:
      name: "No null is_current in dim_customer"

checks for curated.dim_account:
  - missing_count(account_id) = 0:
      name: "No null account IDs"
  - missing_count(customer_id) = 0:
      name: "No null customer IDs in dim_account"
  - missing_count(account_type) = 0:
      name: "No null account types"
  - missing_count(account_status) = 0:
      name: "No null account statuses"
  - missing_count(currency) = 0:
      name: "No null currencies"
  - missing_count(valid_from) = 0:
      name: "No null valid_from in dim_account"
  - missing_count(is_current) = 0:
      name: "No null is_current in dim_account"

checks for curated.dim_device:
  - missing_count(device_id) = 0:
      name: "No null device IDs"
  - missing_count(customer_id) = 0:
      name: "No null customer IDs in dim_device"
  - missing_count(device_type) = 0:
      name: "No null device types"
  - missing_count(ip_address) = 0:
      name: "No null IP addresses"
  - missing_count(valid_from) = 0:
      name: "No null valid_from in dim_device"
  - missing_count(is_current) = 0:
      name: "No null is_current in dim_device"

checks for curated.dim_location:
  - missing_count(location_id) = 0:
      name: "No null location IDs"
  - missing_count(merchant_name) = 0:
      name: "No null merchant names"
  - missing_count(merchant_category) = 0:
      name: "No null merchant categories"
  - missing_count(country) = 0:
      name: "No null countries in locations"
  - missing_count(valid_from) = 0:
      name: "No null valid_from in dim_location"
  - missing_count(is_current) = 0:
      name: "No null is_current in dim_location"

checks for curated.fact_transactions:
  - missing_count(transaction_id) = 0:
      name: "No null transaction IDs"
  - duplicate_count(transaction_id) = 0:
      name: "No duplicate transaction IDs"
  - missing_count(account_id) = 0:
      name: "No null account IDs"
  - missing_count(customer_id) = 0:
      name: "No null customer IDs"
  - missing_count(amount) = 0:
      name: "No null amounts"
  - min(amount) >= 0:
      name: "No negative amounts"
  - missing_count(is_fraud) = 0:
      name: "No null fraud flags"
  - missing_count(transaction_date) = 0:
      name: "No null transaction dates"
  - missing_count(transaction_status) = 0:
      name: "No null transaction statuses"
  - missing_count(currency) = 0:
      name: "No null currencies"
  - missing_count(created_at) = 0:
      name: "No null created_at in fact_transactions"

checks for curated.fact_fraud_alerts:
  - missing_count(transaction_id) = 0:
      name: "No null transaction IDs in alerts"
  - missing_count(customer_id) = 0:
      name: "No null customer IDs in alerts"
  - missing_count(account_id) = 0:
      name: "No null account IDs in alerts"
  - min(amount) >= 0:
      name: "No negative amounts in alerts"
  - missing_count(transaction_date) = 0:
      name: "No null transaction dates in alerts"
""")

    scan.execute()

    if scan.has_check_fails():
        failed_checks = [str(c) for c in scan.get_checks_fail()]
        error_msg = f"Soda DQ Check 2 FAILED: {failed_checks}"
        logger.error(error_msg)
        log_to_db("airflow", "ERROR", "SODA_DQ_CHECK_2", "curated",
                  error_msg, error_details=str(failed_checks))
        raise Exception(error_msg)
    else:
        logger.info("Soda DQ Check 2 PASSED")
        log_to_db("airflow", "INFO", "SODA_DQ_CHECK_2", "curated",
                  "DQ Check 2 passed")



# TASK 10 — UPDATE LAST RUN TIMESTAMP

def update_last_run(**context):
    run_start = context['ti'].xcom_pull(key='run_start', task_ids='check_landing_data')
    set_last_run_timestamp(run_start)
    logger.info(f"Updated last_run to run_start: {run_start}")
    log_to_db("airflow", "INFO", "DAG_COMPLETE", "all_tables",
              f"Pipeline completed. last_run updated to {run_start}")


# -----------------------------------------------------------------------------
# DEFINE TASKS
# -----------------------------------------------------------------------------
t1_check_landing = PythonOperator(
    task_id="check_landing_data",
    python_callable=check_landing_data,
    dag=dag
)

t2_soda_dq1 = PythonOperator(
    task_id="soda_dq_check_1",
    python_callable=soda_dq_check_1,
    dag=dag
)

t3_dim_customer = PythonOperator(
    task_id="load_dim_customer",
    python_callable=load_dim_customer,
    dag=dag
)

t4_dim_account = PythonOperator(
    task_id="load_dim_account",
    python_callable=load_dim_account,
    dag=dag
)

t5_dim_device = PythonOperator(
    task_id="load_dim_device",
    python_callable=load_dim_device,
    dag=dag
)

t6_dim_location = PythonOperator(
    task_id="load_dim_location",
    python_callable=load_dim_location,
    dag=dag
)

t7_fact_transactions = PythonOperator(
    task_id="load_fact_transactions",
    python_callable=load_fact_transactions,
    dag=dag
)

t8_fact_fraud_alerts = PythonOperator(
    task_id="load_fact_fraud_alerts",
    python_callable=load_fact_fraud_alerts,
    dag=dag
)

t9_soda_dq2 = PythonOperator(
    task_id="soda_dq_check_2",
    python_callable=soda_dq_check_2,
    dag=dag
)

t10_update_last_run = PythonOperator(
    task_id="update_last_run",
    python_callable=update_last_run,
    dag=dag
)

# -----------------------------------------------------------------------------
# TASK DEPENDENCIES
# -----------------------------------------------------------------------------
t1_check_landing >> t2_soda_dq1 >> [t3_dim_customer, t4_dim_account, t5_dim_device, t6_dim_location] >> t7_fact_transactions >> t8_fact_fraud_alerts >> t9_soda_dq2 >> t10_update_last_run