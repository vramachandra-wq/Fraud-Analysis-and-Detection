from database.vip_repository import (
    get_vip_details,
    get_vip_volume_metrics,
    upsert_vip_record,
    update_vip_limits,
)
from database.blacklist_repository import is_blacklisted
from database.vip_repository import delete_vip_record


class VIPBlacklistedError(Exception):
    """Raised when trying to add a blacklisted account to VIP tier."""
    pass


def fetch_vip_details(account_id: str) -> dict | None:
    return get_vip_details(account_id)


def fetch_vip_volume(account_id: str) -> tuple[int, object]:
    return get_vip_volume_metrics(account_id)


def provision_vip(account_id: str, amount_limit: float, volume_limit: int) -> None:
    """
    Add or update a VIP record.

    Raises VIPBlacklistedError if the account is currently blacklisted.
    The caller must handle this and offer to whitelist first.
    """
    if is_blacklisted(account_id):
        raise VIPBlacklistedError(
            f"Account **{account_id}** is on the blacklist. "
            "Please whitelist the account before adding it to the VIP tier."
        )
    upsert_vip_record(account_id, amount_limit, volume_limit)


def modify_vip_limits(account_id: str, amount_limit: float, volume_limit: int) -> None:
    update_vip_limits(account_id, amount_limit, volume_limit)


def revoke_vip_status(account_id: str) -> None:
    """Business logic wrapper to revoke VIP status from an account."""
    delete_vip_record(account_id)