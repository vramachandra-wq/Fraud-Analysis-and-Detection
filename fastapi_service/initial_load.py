

import psycopg2
import psycopg2.extras
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("initial_load.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


OLTP_CONFIG = {
    "host": "127.0.0.1",
    "port": 5433,
    "dbname": "fraud_oltp",
    "user": "postgres",
    "password": "Master#123"
}

OLAP_CONFIG = {
    "host": "127.0.0.1",
    "port": 5434,
    "dbname": "fraud_olap",
    "user": "postgres",
    "password": "Master#123"
}

TABLE_MAP = {
    "staging.stg_customers":    "landing.customers",
    "staging.stg_accounts":     "landing.accounts",
    "staging.stg_devices":      "landing.devices",
    "staging.stg_locations":    "landing.locations",
    "staging.stg_transactions": "landing.transactions",  
}

TABLE_COLUMNS = {
    "staging.stg_customers": [
        "customer_id", "first_name", "last_name", "email", "phone",
        "date_of_birth", "gender", "nationality", "address_line1",
        "address_line2", "city", "state", "zip_code", "country",
        "created_at", "updated_at", "is_active", "credit_score",
        "annual_income", "occupation"
    ],
    "staging.stg_accounts": [
        "account_id", "customer_id", "account_number", "account_type",
        "account_status", "bank_name", "routing_number", "currency",
        "balance", "credit_limit", "opening_date", "closing_date",
        "last_transaction_date", "created_at", "updated_at"
    ],
    "staging.stg_devices": [
        "device_id", "customer_id", "device_type", "device_fingerprint",
        "operating_system", "os_version", "browser", "browser_version",
        "ip_address", "mac_address", "is_trusted", "first_seen_at",
        "last_seen_at", "created_at"
    ],
    "staging.stg_locations": [
        "location_id", "merchant_name", "merchant_category", "address_line1",
        "city", "state", "zip_code", "country", "latitude", "longitude",
        "is_high_risk_area", "created_at"
    ],
    "staging.stg_transactions": [
        "transaction_id", "account_id", "device_id", "location_id",
        "transaction_type", "channel", "amount", "currency",
        "transaction_status", "merchant_name", "merchant_category",
        "is_fraud", "fraud_reason", "transaction_date", "transaction_time",
        "processing_time_ms", "created_at", "updated_at",
        "reference_number", "notes"
    ]
}


def log_to_db(olap_conn, table_name, message, rows_affected=0,
              log_level="INFO", error_details=None):
    try:
        with olap_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO logging.pipeline_logs
                (service, log_level, event_type, table_name, message,
                 error_details, rows_affected, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, ("initial_load", log_level, "BULK_COPY", table_name,
                  message, error_details, rows_affected, datetime.utcnow()))
        olap_conn.commit()
    except Exception as e:
        logger.error(f"Failed to write to logging table: {e}")


def get_row_count(conn, table):
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]



def copy_table(oltp_conn, olap_conn, source_table, target_table):
    columns = TABLE_COLUMNS[source_table]
    col_str = ", ".join(columns)
    target_col_str = col_str + ", cdc_operation, cdc_timestamp"

    logger.info(f"Starting copy: {source_table} → {target_table}")
    start_time = datetime.utcnow()

    try:
        oltp_cursor = oltp_conn.cursor()
        olap_cursor = olap_conn.cursor()

        
        import io

        buffer = io.StringIO()
        copy_sql = f"COPY (SELECT {col_str}, 'INSERT' as cdc_operation, NOW() as cdc_timestamp FROM {source_table}) TO STDOUT WITH CSV"
        oltp_cursor.copy_expert(copy_sql, buffer)
        buffer.seek(0)

       
        copy_in_sql = f"COPY {target_table} ({target_col_str}) FROM STDIN WITH CSV"
        olap_cursor.copy_expert(copy_in_sql, buffer)
        olap_conn.commit()

      
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        row_count = get_row_count(olap_conn, target_table)

        logger.info(f"✅ {source_table} → {target_table} | rows={row_count:,} | time={duration:.1f}s")
        log_to_db(olap_conn, target_table,
                  f"Initial load complete: {row_count:,} rows in {duration:.1f}s",
                  rows_affected=row_count)

        return row_count

    except Exception as e:
        olap_conn.rollback()
        logger.error(f"❌ Failed to copy {source_table}: {e}")
        log_to_db(olap_conn, target_table,
                  f"Initial load failed",
                  log_level="ERROR", error_details=str(e))
        raise



def truncate_landing_tables(olap_conn):
    logger.info("Truncating all landing tables...")
    with olap_conn.cursor() as cur:
        for target_table in TABLE_MAP.values():
            cur.execute(f"TRUNCATE TABLE {target_table} CASCADE")
            logger.info(f"Truncated {target_table}")
    olap_conn.commit()
    logger.info("All landing tables truncated ✅")



def main():
    logger.info("=" * 60)
    logger.info("INITIAL LOAD STARTED")
    logger.info("=" * 60)

    total_start = datetime.utcnow()

    try:
       
        logger.info("Connecting to OLTP...")
        oltp_conn = psycopg2.connect(**OLTP_CONFIG)
        oltp_conn.autocommit = True  

        logger.info("Connecting to OLAP...")
        olap_conn = psycopg2.connect(**OLAP_CONFIG)

      
        truncate_landing_tables(olap_conn)

       
        total_rows = 0
        for source_table, target_table in TABLE_MAP.items():
            source_count = get_row_count(oltp_conn, source_table)
            logger.info(f"Source {source_table}: {source_count:,} rows")
            rows = copy_table(oltp_conn, olap_conn, source_table, target_table)
            total_rows += rows

   
        total_duration = (datetime.utcnow() - total_start).total_seconds()
        logger.info("=" * 60)
        logger.info(f"INITIAL LOAD COMPLETE")
        logger.info(f"Total rows loaded: {total_rows:,}")
        logger.info(f"Total time: {total_duration:.1f}s")
        logger.info("=" * 60)

        log_to_db(olap_conn, "all_tables",
                  f"Initial load complete: {total_rows:,} rows in {total_duration:.1f}s",
                  rows_affected=total_rows)

        oltp_conn.close()
        olap_conn.close()

    except Exception as e:
        logger.error(f"Initial load failed: {e}")
        raise


if __name__ == "__main__":
    main()