from database.blacklist_repository import is_blacklisted, add_to_blacklist, remove_from_blacklist


def check_blacklisted(account_id: str) -> bool:
    return is_blacklisted(account_id)


def blacklist_account(account_id: str) -> None:
    add_to_blacklist(account_id)


def whitelist_account(account_id: str) -> None:
    remove_from_blacklist(account_id)
