from __future__ import annotations

import re
from typing import Any

# Phone (KZ/RU), email, BIN, private doc hints.
_PHONE_RE = re.compile(
    r"(?:\+?\d[\d\s().\-]{8,18}\d|"
    r"(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})"
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_BIN_RE = re.compile(r"\b\d{12}\b")
_TOO_RE = re.compile(r"(?i)\b(?:тоо|too|тoo|бин|bin|иин|iin)\b[^\n]{0,80}")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_MESSENGER_RE = re.compile(r"(?i)(?:whatsapp|telegram|t\.me/|wa\.me/|@\w{4,})")

FEED_POST_PROMPT = """Ты редактор постов для публичной ленты фаундеров Kangaroo.
На основе отчёта по шагу напиши короткий пост об апдейте.

Проект: {startup_name}
Шаг: {step_label}

СТРОГО ЗАПРЕЩЕНО включать в title и body:
- телефоны, email, мессенджеры, @username
- BIN, ИИН, номера ТОО, юридические реквизиты, названия юрлиц с реквизитами
- ФИО клиентов, партнёров, сотрудников
- адреса офисов/домов, ссылки на личные документы и приватные URL
- пароли, токены, API-ключи, номера договоров с контрагентами

МОЖНО: название проекта, суть шага, обезличенные метрики, общий прогресс, выводы.
Тон: живой, без воды, от первого лица фаундера. Русский язык.

Верни JSON:
{{
  "title": "короткий заголовок до 80 символов",
  "body": "текст поста 2-5 предложений, до 600 символов"
}}"""


def scrub_private_data(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = _PHONE_RE.sub("[скрыто]", cleaned)
    cleaned = _EMAIL_RE.sub("[скрыто]", cleaned)
    cleaned = _BIN_RE.sub("[скрыто]", cleaned)
    cleaned = _URL_RE.sub("[ссылка скрыта]", cleaned)
    cleaned = _MESSENGER_RE.sub("[скрыто]", cleaned)
    cleaned = _TOO_RE.sub("[реквизиты скрыты]", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def generate_safe_feed_post(
    user,
    startup,
    *,
    step_label: str,
    report: str,
) -> dict[str, Any]:
    from .ai_agent import _json_chat

    report_clean = scrub_private_data(report.strip())
    if len(report_clean) < 10:
        raise ValueError("Напиши отчёт подробнее — от 10 символов.")

    system = FEED_POST_PROMPT.format(
        startup_name=startup.name,
        step_label=step_label,
    )
    data = _json_chat(
        system,
        f"Отчёт фаундера:\n{report_clean[:500]}",
        max_tokens=420,
        temperature=0.35,
    )
    title = scrub_private_data(str(data.get("title") or "")).strip()
    body = scrub_private_data(str(data.get("body") or "")).strip()
    if len(body) < 2:
        raise ValueError("AI не смог составить безопасный пост. Попробуй ещё раз.")
    if not title:
        title = body[:80]
    return {
        "title": title[:160],
        "body": body[:900],
    }
