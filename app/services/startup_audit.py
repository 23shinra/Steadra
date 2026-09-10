"""Compact startup audit rubric derived from «Стартап Прогон.xlsx» (100 questions).

Full 100Q checklist is too large for every roast call. We score 10 blocks (0–5);
each block compresses the Excel sheet section into a short check-list for the model.
Overall score 0–100 is computed server-side from block scores.
"""

from __future__ import annotations

from typing import Any

# id must stay stable — used in JSON and UI.
AUDIT_BLOCKS: list[dict[str, str]] = [
    {
        "id": "basis",
        "label": "Основа",
        "check": "проблема, сегмент, частота/цена боли, текущая альтернатива, срочность, value prop в 1 фразе",
    },
    {
        "id": "custdev",
        "label": "Клиент и CustDev",
        "check": "кто платит / кто решает, блокеры покупки, сигналы спроса или интервью, цикл сделки",
    },
    {
        "id": "market",
        "label": "Рынок",
        "check": "TAM/SAM или размер сегмента, чек/выручка с клиента, рост рынка, география",
    },
    {
        "id": "product",
        "label": "Продукт и MVP",
        "check": "ядро продукта, гипотеза MVP, минимальность, onboarding, канал первых юзеров",
    },
    {
        "id": "acquisition",
        "label": "Привлечение",
        "check": "воронка/конверсии, лучший канал, повторяемость привлечения без основателя",
    },
    {
        "id": "monetization",
        "label": "Монетизация",
        "check": "модель денег, цена, есть ли выручка, предсказуемость, концентрация выручки",
    },
    {
        "id": "unit_econ",
        "label": "Юнит-экономика",
        "check": "CAC, LTV, LTV:CAC, маржа, payback — или честное «ещё нет данных»",
    },
    {
        "id": "retention",
        "label": "Удержание и PMF",
        "check": "churn/retention, повторные действия, рекомендации, доказательства PMF",
    },
    {
        "id": "moat",
        "label": "Конкуренты и MOAT",
        "check": "прямые/косвенные альтернативы, дифференциация vs status quo, что сложно скопировать",
    },
    {
        "id": "team_finance",
        "label": "Команда и финансы",
        "check": "роли в команде, пробелы, burn/runway или этап инвестиций (если уместно)",
    },
]

AUDIT_BLOCK_IDS = {b["id"] for b in AUDIT_BLOCKS}
AUDIT_BLOCK_BY_ID = {b["id"]: b for b in AUDIT_BLOCKS}


def audit_rubric_for_prompt() -> str:
    """Short rubric text for the roast system prompt (token-light)."""
    lines = [
        "Оцени идею по 10 блокам аудита Kangaroo (из чек-листа «100 вопросов»).",
        "Каждый блок: score 0–5. Шкала: 0=нет/провал, 1=слабо, 2=намек, 3=ясная гипотеза,",
        "4=сильная конкретика, 5=доказано фактами. Для сырой идеи без цифр типично 0–3.",
        "Не выдумывай факты: нет данных → низкий балл + note что проверить.",
        "note: до 70 символов, по-русски, без воды.",
        "Блоки:",
    ]
    for b in AUDIT_BLOCKS:
        lines.append(f"- {b['id']}: {b['label']} — {b['check']}")
    return "\n".join(lines)


def normalize_criteria(raw: Any) -> list[dict[str, Any]]:
    """Normalize model criteria into a full 10-block list."""
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "").strip()
            if cid not in AUDIT_BLOCK_IDS:
                continue
            try:
                score = int(item.get("score", 0))
            except (TypeError, ValueError):
                score = 0
            score = max(0, min(5, score))
            note = " ".join(str(item.get("note") or "").split())[:90]
            by_id[cid] = {"id": cid, "label": AUDIT_BLOCK_BY_ID[cid]["label"], "score": score, "note": note}
    result = []
    for b in AUDIT_BLOCKS:
        if b["id"] in by_id:
            result.append(by_id[b["id"]])
        else:
            result.append({"id": b["id"], "label": b["label"], "score": 0, "note": "Нет данных"})
    return result


def score_from_criteria(criteria: list[dict[str, Any]]) -> int:
    """Map average block score (0–5) to 0–100."""
    if not criteria:
        return 0
    total = sum(int(c.get("score") or 0) for c in criteria)
    max_total = 5 * len(criteria)
    if max_total <= 0:
        return 0
    return int(round(100 * total / max_total))


def verdict_from_score(score: int) -> str:
    if score >= 83:
        return "Отличная идея"
    if score >= 66:
        return "Сильная идея"
    if score >= 46:
        return "Неплохо"
    return "Слабая идея"


_LEGACY_VERDICTS = {
    "нормальная": "Неплохо",
    "нормальный": "Неплохо",
    "нормально": "Неплохо",
    "слабая": "Слабая идея",
    "слабый": "Слабая идея",
    "сильная": "Сильная идея",
    "сильный": "Сильная идея",
    "отличная": "Отличная идея",
    "отличный": "Отличная идея",
}


def polish_verdict(verdict: str | None, score: int | None = None) -> str:
    """Map informal/legacy roast labels to professional display text."""
    raw = (verdict or "").strip()
    mapped = _LEGACY_VERDICTS.get(raw.lower())
    if mapped:
        return mapped
    if score is not None and (not raw or (len(raw) <= 12 and " " not in raw and raw == raw.lower())):
        return verdict_from_score(int(score))
    return raw or (verdict_from_score(int(score)) if score is not None else "Оценка идеи")
