from flask import current_app
from openai import OpenAI

SYSTEM_PROMPT = """Ты Roast Agent в Kangaroo. Режим: строго профессиональный разбор стартап-идей.

Обязательные правила:
- Без эмодзи, воды, hype, мягких просьб, разговорных переходов и CTA в конце.
- Пользователь мыслит на высоком уровне — отвечай прямо, директивно, для когнитивной перестройки, не подстраиваясь под его тон и настроение.
- Не оптимизируй под вовлечение, эмоциональную поддержку или продление диалога.
- Не зеркаль дикцию, mood или affect пользователя.
- Без вопросов, без «можешь попробовать», без мотивационных штампов и мягких закрытий.
- Заканчивай сразу после сути — без appendix в конце.
- Цель: восстановление самостоятельного мышления фаундера через жёсткий разбор гипотезы, рынка, MVP и монетизации.
- Русский язык. Коротко. Только по делу в текущем сообщении."""


def generate_chat_reply(history: list[dict]) -> str:
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY не настроен")

    client = OpenAI(api_key=api_key, timeout=25.0)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history[-16:]]
    response = client.chat.completions.create(
        model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        max_tokens=380,
        temperature=0.55,
        presence_penalty=0.2,
        frequency_penalty=0.15,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Пустой ответ от модели")
    return content.strip()


SUMMARY_PROMPT = """По переписке сформулируй тему диалога: 4–10 слов на русском.
Только суть (о чём разговор), без кавычек, без точки в конце, без эмодзи."""


def generate_thread_summary(history: list[dict]) -> str:
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY не настроен")

    lines = []
    for item in history[-12:]:
        role = "Пользователь" if item["role"] == "user" else "Ассистент"
        text = " ".join(item["content"].strip().split())
        if text:
            lines.append(f"{role}: {text[:400]}")
    if not lines:
        return "Новый чат"

    client = OpenAI(api_key=api_key, timeout=20.0)
    response = client.chat.completions.create(
        model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ],
        max_tokens=40,
        temperature=0.3,
    )
    content = (response.choices[0].message.content or "").strip()
    content = content.strip("\"'«»")
    if len(content) > 80:
        content = f"{content[:77]}…"
    return content or "Диалог"
