from database.connection import get_db_connection


def is_valid_account(account_id: str) -> bool:
    """Return True if the account exists in lookup.valid_accounts."""
    with get_db_connection().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM lookup.valid_accounts WHERE account_id = %s;",
            (str(account_id),),
        )
        return cur.fetchone() is not None
