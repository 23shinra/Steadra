INVESTOR_ROLE_ID = "investor"
INVESTOR_ROLE_LABEL = "Инвестор"

ROLES = [
    {
        "id": "founder",
        "label": "Основатель",
        "icon": "rocket",
    },
    {
        "id": "saas",
        "label": "B2B SaaS основатель",
        "icon": "briefcase",
    },
    {
        "id": "product",
        "label": "Создатель продукта",
        "icon": "layers",
    },
    {
        "id": "growth",
        "label": "Growth-лид",
        "icon": "chart",
    },
    {
        "id": "ai",
        "label": "AI-билдер",
        "icon": "spark",
    },
    {
        "id": "design",
        "label": "UX / Дизайн",
        "icon": "pen",
    },
    {
        "id": "ops",
        "label": "Операции",
        "icon": "gear",
    },
]

LEGACY_ROLE_LABELS = {
    "Founder": "Основатель",
    "B2B SaaS founder": "B2B SaaS основатель",
    "Product maker": "Создатель продукта",
    "Growth lead": "Growth-лид",
    "AI builder": "AI-билдер",
    "UX / Design": "UX / Дизайн",
    "Operations": "Операции",
    "Investor": INVESTOR_ROLE_LABEL,
}

ROLE_BY_ID = {role["id"]: role for role in ROLES}
ROLE_BY_ID[INVESTOR_ROLE_ID] = {"id": INVESTOR_ROLE_ID, "label": INVESTOR_ROLE_LABEL, "icon": "briefcase"}
ROLE_LABELS = {role["label"] for role in ROLES} | {INVESTOR_ROLE_LABEL}


def founder_roles() -> list[dict]:
    return ROLES


def display_role(role_value: str | None) -> str:
    if not role_value:
        return ROLES[0]["label"]
    if role_value in {INVESTOR_ROLE_LABEL, "Investor"}:
        return INVESTOR_ROLE_LABEL
    if role_value in LEGACY_ROLE_LABELS:
        return LEGACY_ROLE_LABELS[role_value]
    if role_value in ROLE_LABELS:
        return role_value
    return role_value


def role_id_for_user(role_value: str | None) -> str:
    if not role_value:
        return ROLES[0]["id"]
    if role_value in {INVESTOR_ROLE_LABEL, "Investor"}:
        return INVESTOR_ROLE_ID
    normalized = LEGACY_ROLE_LABELS.get(role_value, role_value)
    if normalized in ROLE_BY_ID:
        for role_id, role in ROLE_BY_ID.items():
            if role["label"] == normalized:
                return role_id
    for role in ROLES:
        if role["label"] == role_value or role["label"] == normalized:
            return role["id"]
    return ROLES[0]["id"]


def role_label_for_id(role_id: str | None) -> str:
    if role_id == INVESTOR_ROLE_ID:
        return INVESTOR_ROLE_LABEL
    role = ROLE_BY_ID.get(role_id or "")
    return role["label"] if role else ROLES[0]["label"]


def is_valid_role_id(role_id: str | None) -> bool:
    return bool(role_id and role_id in ROLE_BY_ID)
