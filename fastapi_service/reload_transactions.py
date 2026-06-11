

import psycopg2
import logging
from datetime import datetime
import io

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

OLTP_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "fraud_oltp",
    "user": "postgres",
    "password": "Master#123"
}

OLAP_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "fraud_olap",
    "user": "postgres",
    "password": "Master#123"
}

COLUMNS = """transaction_id, account_id, device_id, location_id,
    transaction_type, channel, amount, currency,
    transaction_status, merchant_name, merchant_category,
    is_fraud, fraud_reason, transaction_date, transaction_time,
    processing_time_ms, created_at, updated_at,
    reference_number, notes"""

def main():
    logger.info("Starting reload of landing.transactions...")
    start = datetime.utcnow()

    oltp_conn = psycopg2.connect(**OLTP_CONFIG)
    oltp_conn.autocommit = True
    olap_conn = psycopg2.connect(**OLAP_CONFIG)

  
    with olap_conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE landing.transactions")
    olap_conn.commit()
    logger.info("Truncated landing.transactions")

 
    buffer = io.StringIO()
    with oltp_conn.cursor() as cur:
        cur.copy_expert(
            f"COPY (SELECT {COLUMNS}, 'INSERT' as cdc_operation, NOW() as cdc_timestamp FROM staging.stg_transactions) TO STDOUT WITH CSV",
            buffer
        )
    buffer.seek(0)

    with olap_conn.cursor() as cur:
        cur.copy_expert(
            f"COPY landing.transactions ({COLUMNS}, cdc_operation, cdc_timestamp) FROM STDIN WITH CSV",
            buffer
        )
    olap_conn.commit()

  
    with olap_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM landing.transactions")
        count = cur.fetchone()[0]

    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(f"Done! Loaded {count:,} rows in {duration:.1f}s")

    oltp_conn.close()
    olap_conn.close()

if __name__ == "__main__":
    main()