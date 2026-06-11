from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import psycopg2
import logging

logger = logging.getLogger(__name__)

default_args = {
    "owner": "fraud_pipeline",
    "depends_on_past": False,
    "start_date": datetime(2026, 4, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5)
}

dag = DAG(
    dag_id="aggregation_dag",
    default_args=default_args,
    schedule_interval=timedelta(hours=1),
    catchup=False
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


def get_last_run():
    try:
        return Variable.get("aggregation_last_run")
    except:
        return "1970-01-01 00:00:00"


def set_last_run(ts):
    Variable.set("aggregation_last_run", str(ts))


# --------------------------------
# FRAUD KPI
# --------------------------------
def load_fraud_kpi():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.fraud_kpi_summary
        SELECT
            1,
            COUNT(*),
            COUNT(*) FILTER (WHERE is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE is_fraud)::numeric 
                / NULLIF(COUNT(*), 0) * 100, 2
            ),
            COALESCE(SUM(amount) FILTER (WHERE is_fraud), 0),
            COALESCE(AVG(amount), 0),
            NOW()
        FROM curated.fact_transactions
        WHERE dwh_created_at > '{last_run}'
        ON CONFLICT (id)
        DO UPDATE SET
            total_transactions =
                aggregated.fraud_kpi_summary.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.fraud_kpi_summary.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.fraud_kpi_summary.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()
# --------------------------------
# FRAUD TREND
# --------------------------------
def load_fraud_trend():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.fraud_trend
        SELECT
            transaction_date,
            COUNT(*),
            COUNT(*) FILTER (WHERE is_fraud),
            SUM(amount) FILTER (WHERE is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE is_fraud)::numeric / COUNT(*) * 100,2
            ),
            NOW()
        FROM curated.fact_transactions
        WHERE dwh_created_at > '{last_run}'
        GROUP BY transaction_date
        ON CONFLICT (transaction_date)
        DO UPDATE SET
            total_transactions =
                aggregated.fraud_trend.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.fraud_trend.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.fraud_trend.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# FRAUD BY MCC
# --------------------------------
def load_fraud_by_mcc():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.fraud_by_mcc
        SELECT
            dl.merchant_category,
            COUNT(*),
            COUNT(*) FILTER (WHERE ft.is_fraud),
            SUM(ft.amount) FILTER (WHERE ft.is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE ft.is_fraud)::numeric / COUNT(*) * 100,2
            ),
            NOW()
        FROM curated.fact_transactions ft
        JOIN curated.dim_location dl
            ON ft.location_id = dl.location_id
            AND dl.is_current = true
        WHERE ft.dwh_created_at > '{last_run}'
        GROUP BY dl.merchant_category
        ON CONFLICT (merchant_category)
        DO UPDATE SET
            total_transactions =
                aggregated.fraud_by_mcc.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.fraud_by_mcc.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.fraud_by_mcc.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# GEO FRAUD
# --------------------------------
def load_geo_fraud():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.geo_fraud_summary
        SELECT
            COALESCE(dl.country,'Unknown'),
            COALESCE(dl.state,'Unknown'),
            COALESCE(dl.city,'Unknown'),
            COUNT(*),
            COUNT(*) FILTER (WHERE ft.is_fraud),
            SUM(ft.amount) FILTER (WHERE ft.is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE ft.is_fraud)::numeric / COUNT(*) * 100,2
            ),
            NOW()
        FROM curated.fact_transactions ft
        JOIN curated.dim_location dl
            ON ft.location_id = dl.location_id
            AND dl.is_current = true
        WHERE ft.dwh_created_at > '{last_run}'
        GROUP BY dl.country, dl.state, dl.city
        ON CONFLICT (country,state,city)
        DO UPDATE SET
            total_transactions =
                aggregated.geo_fraud_summary.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.geo_fraud_summary.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.geo_fraud_summary.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# CHANNEL FRAUD
# --------------------------------
def load_channel_fraud():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.channel_fraud_summary
        SELECT
            channel,
            COUNT(*),
            COUNT(*) FILTER (WHERE is_fraud),
            SUM(amount) FILTER (WHERE is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE is_fraud)::numeric / COUNT(*) * 100,2
            ),
            NOW()
        FROM curated.fact_transactions
        WHERE dwh_created_at > '{last_run}'
        GROUP BY channel
        ON CONFLICT (channel)
        DO UPDATE SET
            total_transactions =
                aggregated.channel_fraud_summary.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.channel_fraud_summary.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.channel_fraud_summary.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# CUSTOMER RISK
# --------------------------------
def load_customer_risk():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.customer_risk_summary
        SELECT
            customer_id,
            COUNT(*),
            COUNT(*) FILTER (WHERE is_fraud),
            SUM(amount) FILTER (WHERE is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE is_fraud)::numeric / COUNT(*) * 100,2
            ),
            AVG(amount),
            MAX(amount),
            NOW()
        FROM curated.fact_transactions
        WHERE dwh_created_at > '{last_run}'
        GROUP BY customer_id
        ON CONFLICT (customer_id)
        DO UPDATE SET
            total_transactions =
                aggregated.customer_risk_summary.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.customer_risk_summary.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.customer_risk_summary.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# MERCHANT RISK
# --------------------------------
def load_merchant_risk():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.merchant_risk_summary
        SELECT
            dl.merchant_name,
            dl.merchant_category,
            COUNT(*),
            COUNT(*) FILTER (WHERE ft.is_fraud),
            SUM(ft.amount) FILTER (WHERE ft.is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE ft.is_fraud)::numeric / COUNT(*) * 100,2
            ),
            NOW()
        FROM curated.fact_transactions ft
        JOIN curated.dim_location dl
            ON ft.location_id = dl.location_id
            AND dl.is_current = true
        WHERE ft.dwh_created_at > '{last_run}'
        GROUP BY dl.merchant_name, dl.merchant_category
        ON CONFLICT (merchant_name, merchant_category)
        DO UPDATE SET
            total_transactions =
                aggregated.merchant_risk_summary.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.merchant_risk_summary.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_amount =
                aggregated.merchant_risk_summary.fraud_amount + EXCLUDED.fraud_amount,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# DEVICE RISK
# --------------------------------
def load_device_risk():
    conn = get_conn()
    last_run = get_last_run()

    with conn.cursor() as cur:
        cur.execute(f"""
        INSERT INTO aggregated.device_risk_summary
        SELECT
            dd.device_type,
            dd.is_trusted,
            COUNT(*),
            COUNT(*) FILTER (WHERE ft.is_fraud),
            ROUND(
                COUNT(*) FILTER (WHERE ft.is_fraud)::numeric / COUNT(*) * 100,2
            ),
            NOW()
        FROM curated.fact_transactions ft
        JOIN curated.dim_device dd
            ON ft.device_id = dd.device_id
            AND dd.is_current = true
        WHERE ft.dwh_created_at > '{last_run}'
        GROUP BY dd.device_type, dd.is_trusted
        ON CONFLICT (device_type,is_trusted)
        DO UPDATE SET
            total_transactions =
                aggregated.device_risk_summary.total_transactions + EXCLUDED.total_transactions,
            fraud_transactions =
                aggregated.device_risk_summary.fraud_transactions + EXCLUDED.fraud_transactions,
            fraud_rate = EXCLUDED.fraud_rate,
            last_updated = NOW();
        """)

    conn.commit()
    conn.close()


# --------------------------------
# UPDATE LAST RUN
# --------------------------------
def update_last_run():
    conn = get_conn()

    with conn.cursor() as cur:
        cur.execute("""
        SELECT MAX(dwh_created_at)
        FROM curated.fact_transactions
        """)

        ts = cur.fetchone()[0]

    set_last_run(ts)
    conn.close()


# --------------------------------
# TASKS
# --------------------------------

start = PythonOperator(
    task_id="start",
    python_callable=lambda: print("start"),
    dag=dag
)

t1 = PythonOperator(task_id="fraud_kpi", python_callable=load_fraud_kpi, dag=dag)
t2 = PythonOperator(task_id="fraud_trend", python_callable=load_fraud_trend, dag=dag)
t3 = PythonOperator(task_id="fraud_by_mcc", python_callable=load_fraud_by_mcc, dag=dag)
t4 = PythonOperator(task_id="geo_fraud", python_callable=load_geo_fraud, dag=dag)
t5 = PythonOperator(task_id="channel_fraud", python_callable=load_channel_fraud, dag=dag)
t6 = PythonOperator(task_id="customer_risk", python_callable=load_customer_risk, dag=dag)
t7 = PythonOperator(task_id="merchant_risk", python_callable=load_merchant_risk, dag=dag)
t8 = PythonOperator(task_id="device_risk", python_callable=load_device_risk, dag=dag)

end = PythonOperator(
    task_id="update_last_run",
    python_callable=update_last_run,
    dag=dag
)

start >> [t1, t2, t3, t4, t5, t6, t7, t8] >> end