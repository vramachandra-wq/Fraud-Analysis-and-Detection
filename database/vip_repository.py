import datetime
from psycopg2.extras import RealDictCursor
from database.connection import get_db_connection


def get_vip_details(account_id: str) -> dict | None:
    """Return VIP limits for an account, or None if not VIP."""
    with get_db_connection().cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT amount_per_transaction_limit, transactions_limit "
            "FROM lookup.vip_accounts WHERE account_id = %s;",
            (str(account_id),),
        )
        return cur.fetchone()


def get_vip_volume_metrics(account_id: str) -> tuple[int, object]:
    """Return (today_tx_count, last_transaction_time) for a VIP account."""
    today = datetime.date.today()
    with get_db_connection().cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)::int AS current_count,
                MAX(transaction_time) AS last_transaction_time
            FROM ml_predictions.transaction_logs
            WHERE account_id = %s AND transaction_date = %s;
            """,
            (str(account_id), today),
        )
        res = cur.fetchone()
        if res and res["current_count"] is not None:
            return res["current_count"], res["last_transaction_time"]
        return 0, None


def upsert_vip_record(account_id: str, amount_limit: float, volume_limit: int) -> None:
    """Insert or update a VIP record."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        # 1. Try updating first
        cur.execute(
            """
            UPDATE lookup.vip_accounts
            SET amount_per_transaction_limit = %s,
                transactions_limit = %s
            WHERE account_id = %s;
            """,
            (amount_limit, int(volume_limit), str(account_id)),
        )
        
        # 2. If no rows were updated, insert it
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO lookup.vip_accounts
                    (account_id, amount_per_transaction_limit, transactions_limit)
                VALUES (%s, %s, %s);
                """,
                (str(account_id), amount_limit, int(volume_limit)),
            )
            
    # CRITICAL: Commit the transaction so Postgres saves it
    conn.commit()


def update_vip_limits(account_id: str, amount_limit: float, volume_limit: int) -> None:
    """Update existing VIP limits."""
    with get_db_connection().cursor() as cur:
        cur.execute(
            """
            UPDATE lookup.vip_accounts
            SET amount_per_transaction_limit = %s,
                transactions_limit = %s
            WHERE account_id = %s;
            """,
            (amount_limit, int(volume_limit), str(account_id)),
        )
