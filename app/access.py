ACCOUNT_USER = "user"
ACCOUNT_INVESTOR = "investor"

ACCOUNT_TYPES = [
    {"id": ACCOUNT_USER, "label": "Основатель"},
    {"id": ACCOUNT_INVESTOR, "label": "Инвестор"},
]


def normalize_account_type(value: str | None) -> str:
    if value == ACCOUNT_INVESTOR:
        return ACCOUNT_INVESTOR
    return ACCOUNT_USER


def is_investor(user) -> bool:
    return bool(user and getattr(user, "account_type", ACCOUNT_USER) == ACCOUNT_INVESTOR)


def account_type_label(value: str | None) -> str:
    for item in ACCOUNT_TYPES:
        if item["id"] == value:
            return item["label"]
    return "Основатель"
