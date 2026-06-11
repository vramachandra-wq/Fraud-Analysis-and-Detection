
import base64
import json
import logging
import struct
import threading
import time
from datetime import date, datetime, timedelta, time as time_type

import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from kafka import KafkaConsumer

# LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("fastapi_cdc.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# CONFIG
KAFKA_BOOTSTRAP_SERVERS = "127.0.0.1:29092"
KAFKA_GROUP_ID = "fastapi-cdc-consumer"
KAFKA_TOPICS = [
    "fraud_oltp.staging.stg_customers",
    "fraud_oltp.staging.stg_accounts",
    "fraud_oltp.staging.stg_transactions",
    "fraud_oltp.staging.stg_devices",
    "fraud_oltp.staging.stg_locations"
]

OLAP_DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "fraud_olap",
    "user": "postgres",
    "password": "Master#123"
}

# Map Kafka topic -> landing table
TOPIC_TABLE_MAP = {
    "fraud_oltp.staging.stg_customers":    "landing.customers",
    "fraud_oltp.staging.stg_accounts":     "landing.accounts",
    "fraud_oltp.staging.stg_transactions": "landing.transactions",
    "fraud_oltp.staging.stg_devices":      "landing.devices",
    "fraud_oltp.staging.stg_locations":    "landing.locations"
}

# Business key per table (for logging only, not for PK constraint)
TABLE_BK_MAP = {
    "landing.customers":    "customer_id",
    "landing.accounts":     "account_id",
    "landing.transactions": "transaction_id",
    "landing.devices":      "device_id",
    "landing.locations":    "location_id"
}

# Date columns — Debezium sends as epoch days
DATE_COLUMNS = {
    "date_of_birth", "opening_date", "closing_date",
    "last_transaction_date", "transaction_date"
}

# Timestamp columns — Debezium sends as epoch milliseconds
TIMESTAMP_COLUMNS = {
    "created_at", "updated_at", "first_seen_at", "last_seen_at"
}

# Time columns — Debezium sends as microseconds since midnight
TIME_COLUMNS = {"transaction_time"}

# Boolean columns
BOOLEAN_COLUMNS = {
    "is_active", "is_fraud", "is_trusted", "is_high_risk_area"
}

# Base64 encoded numeric columns
BASE64_NUMERIC_COLUMNS = {
    "latitude", "longitude", "amount", "balance",
    "credit_limit", "annual_income"
}

# Operation map
OP_MAP = {
    "c": "INSERT",
    "r": "INSERT",
    "u": "UPDATE",
    "d": "DELETE"
}

# BATCH CONFIG
BATCH_SIZE = 1000
BATCH_FLUSH_INTERVAL = 5

# Buffer stores list of (table, data_dict) tuples
batch_buffer = []
batch_lock = threading.Lock()
last_flush_time = time.time()

# FASTAPI APP
app = FastAPI(title="Historical CDC Kafka to OLAP Landing Bridge")

# DB CONNECTION
def get_olap_connection():
    return psycopg2.connect(**OLAP_DB_CONFIG)


def ensure_connection(conn):
    try:
        conn.cursor().execute("SELECT 1")
        return conn
    except Exception:
        logger.warning("DB connection lost, reconnecting...")
        try:
            conn.close()
        except Exception:
            pass
        return get_olap_connection()


# DB LOGGER
def log_to_db(service, log_level, event_type, table_name, message,
              error_details=None, rows_affected=0):
    try:
        log_conn = get_olap_connection()
        with log_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO logging.pipeline_logs
                (service, log_level, event_type, table_name, message,
                 error_details, rows_affected, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (service, log_level, event_type, table_name,
                  message, error_details, rows_affected, datetime.utcnow()))
        log_conn.commit()
        log_conn.close()
    except Exception as e:
        logger.error(f"Failed to write to logging table: {e}")


# DEBEZIUM TYPE CONVERSION
def decode_debezium_value(key, val):
    if val is None:
        return None

    if key in BOOLEAN_COLUMNS:
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return bool(val)
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return None

    if key in DATE_COLUMNS:
        if isinstance(val, int):
            try:
                return date(1970, 1, 1) + timedelta(days=val)
            except Exception:
                return None
        return val

    if key in TIMESTAMP_COLUMNS:
        if isinstance(val, int):
            try:
                return datetime(1970, 1, 1) + timedelta(milliseconds=val)
            except Exception:
                return None
        return val

    if key in TIME_COLUMNS:
        if isinstance(val, int):
            try:
                total_seconds = val // 1_000_000
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return time_type(hours % 24, minutes, seconds)
            except Exception:
                return None
        return val

    if key in BASE64_NUMERIC_COLUMNS and isinstance(val, str):
        try:
            decoded = base64.b64decode(val)
            if len(decoded) == 4:
                return round(float(struct.unpack('>f', decoded)[0]), 6)
            elif len(decoded) == 8:
                return round(float(struct.unpack('>d', decoded)[0]), 6)
            else:
                raw = int.from_bytes(decoded, byteorder='big', signed=True)
                if key in ("latitude", "longitude"):
                    return round(raw / 1_000_000, 6)
                return round(raw / 100, 2)
        except Exception:
            return None

    if isinstance(val, dict):
        return json.dumps(val)

    return val


def clean_data(data: dict) -> dict:
    return {k: decode_debezium_value(k, v) for k, v in data.items()}


# BATCH FLUSH — Append-Only INSERT

def flush_batch(conn):
    global last_flush_time

    with batch_lock:
        if not batch_buffer:
            return
        to_flush = batch_buffer.copy()
        batch_buffer.clear()
        last_flush_time = time.time()

    # Group by table
    table_groups = {}
    for table, data in to_flush:
        if table not in table_groups:
            table_groups[table] = []
        table_groups[table].append(data)

    try:
        with conn.cursor() as cur:
            for table, rows in table_groups.items():
                if not rows:
                    continue

                # Get columns from first row (exclude event_id — auto generated)
                sample = rows[0]
                columns = [c for c in sample.keys() if c != "event_id"]
                col_str = ", ".join(columns)
                placeholders = ", ".join(["%s"] * len(columns))

                sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"

                # Batch insert all rows
                psycopg2.extras.execute_batch(
                    cur,
                    sql,
                    [[row.get(col) for col in columns] for row in rows],
                    page_size=500
                )

                logger.info(f"FLUSH {table} -> {len(rows)} rows appended")
                log_to_db("fastapi", "INFO", "BATCH_FLUSH", table,
                          f"Appended {len(rows)} CDC events", rows_affected=len(rows))

        conn.commit()

    except Exception as e:
        logger.error(f"Batch flush error: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        log_to_db("fastapi", "ERROR", "BATCH_FLUSH_ERROR", "landing",
                  "Batch flush failed", error_details=str(e))



def process_message(msg, conn):
    table = None
    operation = None

    try:
        raw = msg.value
        if raw is None:
            return

        value = json.loads(raw.decode("utf-8"))
        topic = msg.topic
        table = TOPIC_TABLE_MAP.get(topic)

        if not table:
            return

        # Unwrap Debezium payload wrapper
        if "payload" in value:
            value = value["payload"]

        operation = value.get("op")
        bk = TABLE_BK_MAP[table]

        if operation in ("c", "r"):
            # INSERT — use 'after' data
            data = value.get("after") or {}
            if data:
                data = clean_data(data)
                data["cdc_operation"] = "INSERT"
                data["cdc_timestamp"] = datetime.utcnow()
                with batch_lock:
                    batch_buffer.append((table, data))
                logger.debug(f"Queued INSERT -> {table} | {bk}={data.get(bk)}")

        elif operation == "u":
            # UPDATE — use 'after' data, store as UPDATE event
            data = value.get("after") or {}
            if data:
                data = clean_data(data)
                data["cdc_operation"] = "UPDATE"
                data["cdc_timestamp"] = datetime.utcnow()
                with batch_lock:
                    batch_buffer.append((table, data))
                logger.debug(f"Queued UPDATE -> {table} | {bk}={data.get(bk)}")

        elif operation == "d":
            # DELETE — use 'before' data, store as DELETE event
            data = value.get("before") or {}
            if data:
                data = clean_data(data)
                data["cdc_operation"] = "DELETE"
                data["cdc_timestamp"] = datetime.utcnow()
                with batch_lock:
                    batch_buffer.append((table, data))
                logger.debug(f"Queued DELETE -> {table} | {bk}={data.get(bk)}")

        elif operation is None:
            # Snapshot read
            data = value.get("after") or {}
            if data and isinstance(data, dict):
                data = clean_data(data)
                data["cdc_operation"] = "INSERT"
                data["cdc_timestamp"] = datetime.utcnow()
                with batch_lock:
                    batch_buffer.append((table, data))

        # Flush if batch is full
        with batch_lock:
            buffer_size = len(batch_buffer)

        if buffer_size >= BATCH_SIZE:
            flush_batch(conn)
        elif time.time() - last_flush_time >= BATCH_FLUSH_INTERVAL:
            flush_batch(conn)

    except Exception as e:
        logger.error(f"Error processing message from {table}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        log_to_db("fastapi", "ERROR",
                  OP_MAP.get(operation, "UNKNOWN") if operation else "UNKNOWN",
                  table or "unknown",
                  "Error processing CDC event", error_details=str(e))


# KAFKA CONSUMER THREAD
def start_kafka_consumer():
    logger.info("Starting Historical CDC Kafka consumer...")
    try:
        consumer = KafkaConsumer(
            *KAFKA_TOPICS,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=None,
            request_timeout_ms=30000,
            session_timeout_ms=10000,
            heartbeat_interval_ms=3000,
            connections_max_idle_ms=90000,
            fetch_max_bytes=52428800,
            max_partition_fetch_bytes=10485760,
            fetch_min_bytes=1,
            fetch_max_wait_ms=500,
            api_version=(2, 6, 0),
            api_version_auto_timeout_ms=30000
        )
        conn = get_olap_connection()
        logger.info("Kafka consumer connected. Listening for CDC events...")

        for msg in consumer:
            conn = ensure_connection(conn)
            process_message(msg, conn)

    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")


# STARTUP
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=start_kafka_consumer, daemon=True)
    thread.start()
    logger.info("Historical CDC consumer thread started.")


# ENDPOINTS
@app.get("/health")
def health_check():
    return {"status": "running", "timestamp": datetime.utcnow().isoformat()}


@app.get("/")
def root():
    return {"message": "Historical CDC Kafka to OLAP Landing Bridge is running"}


@app.get("/logs")
def get_logs():
    try:
        conn = get_olap_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM logging.pipeline_logs
                ORDER BY created_at DESC
                LIMIT 50
            """)
            logs = cur.fetchall()
        conn.close()
        return {"logs": [dict(row) for row in logs]}
    except Exception as e:
        return {"error": str(e)}


@app.get("/status")
def get_status():
    with batch_lock:
        buffer_size = len(batch_buffer)
    return {
        "buffer_size": buffer_size,
        "batch_size": BATCH_SIZE,
        "flush_interval_seconds": BATCH_FLUSH_INTERVAL
    }