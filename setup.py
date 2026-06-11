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

# Database connection
olap_conn = psycopg2.connect(
    host="127.0.0.1",
    port=5434,
    dbname="fraud_olap",
    user="postgres",       # Replace with your Credentials
    password="Master#123", # Replace with your Credentials
)

oltp_conn = psycopg2.connect(
    host="127.0.0.1",
    port=5433,
    dbname="fraud_oltp",
    user="postgres",       # Replace with your Credentials
    password="Master#123", # Replace with your Credentials

)

# OLTP schema
try:
    execute_sql_file(
        connection=oltp_conn,
        file_path=r"sql\schema_setup\oltp\ddl.sql"
    )
finally:
    oltp_conn.close()


# OLAP schemas
try:
    sql_files = [
        r"sql\schema_setup\olap\logging.sql",
        r"sql\schema_setup\olap\landing.sql",
        r"sql\schema_setup\olap\curated.sql",
        r"sql\schema_setup\olap\aggregated.sql",
        r"sql\ai_chatbot_logs.sql",
        r"sql\ml_transaction_logs.sql",
        r"sql\lookup_table_schema_creation.sql",
        r"sql\rules_engine_function.sql"
    ]

    for file_path in sql_files:
        execute_sql_file(
            connection=olap_conn,
            file_path=file_path
        )
finally:
    olap_conn.close()