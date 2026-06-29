import psycopg2


def execute_sql_file(connection, file_path):
    """
    Execute a SQL script from a file.
    Args:
        connection: psycopg2 connection object
        file_path (str): Path to the SQL file
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            sql_script = file.read()

        with connection.cursor() as cursor:
            cursor.execute(sql_script)

        connection.commit()
        print(f"Successfully executed: {file_path}")

    except Exception as e:
        connection.rollback()
        print(f"Error executing {file_path}: {e}")
        raise


def create_airflow_database():
    """
    Create airflow_db using an autocommit connection.
    """
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5434,
        dbname="postgres",
        user="postgres",
        password="Master#123",
    )

    try:
        conn.autocommit = True

        with open(
            r"sql\create_olap_airflow_db.sql",
            "r",
            encoding="utf-8"
        ) as file:
            sql_script = file.read()

        with conn.cursor() as cursor:
            cursor.execute(sql_script)

        print("Successfully created airflow_db")

    except Exception as e:
        print(f"Error creating airflow_db: {e}")
        raise

    finally:
        conn.close()


# ---------------------------
# Create airflow database first
# ---------------------------

create_airflow_database()

# ---------------------------
# OLTP Connection
# ---------------------------

oltp_conn = psycopg2.connect(
    host="127.0.0.1",
    port=5433,
    dbname="fraud_oltp",
    user="postgres",
    password="Master#123",
)

try:
    execute_sql_file(
        connection=oltp_conn,
        file_path=r"sql\schema_setup\oltp\ddl.sql"
    )
finally:
    oltp_conn.close()

# ---------------------------
# OLAP Connection
# ---------------------------

olap_conn = psycopg2.connect(
    host="127.0.0.1",
    port=5434,
    dbname="fraud_olap",
    user="postgres",
    password="Master#123",
)

try:
    sql_files = [
        r"sql\schema_setup\olap\logging.sql",
        r"sql\schema_setup\olap\landing.sql",
        r"sql\schema_setup\olap\curated.sql",
        r"sql\schema_setup\olap\aggregated.sql",
        r"sql\ai_chatbot_logs.sql",
        r"sql\ml_transaction_logs.sql",
        r"sql\lookup_table_schema_creation.sql",
        r"sql\rules_engine_function.sql",
        r"sql\user_credentials_creation.sql",
        r"sql\user_sessions_table_creation.sql"
    ]

    for file_path in sql_files:
        execute_sql_file(
            connection=olap_conn,
            file_path=file_path
        )

finally:
    olap_conn.close()

print("Database setup completed successfully.")