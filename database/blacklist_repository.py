from database.connection import get_db_connection


def is_blacklisted(account_id: str) -> bool:
    """Return True if the account is on the blacklist."""
    with get_db_connection().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM lookup.blacklist_accounts WHERE account_id = %s;",
            (str(account_id),),
        )
        return cur.fetchone() is not None


def add_to_blacklist(account_id: str) -> None:
    """Insert account into the blacklist (no-op on conflict)."""
    with get_db_connection().cursor() as cur:
        cur.execute(
            "INSERT INTO lookup.blacklist_accounts (account_id) VALUES (%s) ON CONFLICT DO NOTHING;",
            (str(account_id),),
        )


def remove_from_blacklist(account_id: str) -> None:
    """Remove an account from the blacklist (whitelist it)."""
    with get_db_connection().cursor() as cur:
        cur.execute(
            "DELETE FROM lookup.blacklist_accounts WHERE account_id = %s;",
            (str(account_id),),
        )
