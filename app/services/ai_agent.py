import json
from typing import Any

from flask import current_app
from openai import OpenAI

from .roadmap import ROADMAP_STEPS, normalize_steps
from .step_prompts import STEP_VALIDATION_JSON, infer_step_key, step_prompt_for


def _client() -> OpenAI:
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY не настроен")
    return OpenAI(api_key=api_key, timeout=45.0)


def _json_chat(system: str, user: str, max_tokens: int = 520, temperature: float = 0.5) -> dict[str, Any]:
    response = _client().chat.completions.create(
        model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=temperature,
    )
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


def _history_text(history: list[dict], limit: int = 20) -> str:
    lines = []
    for item in history[-limit:]:
        role = "Пользователь" if item["role"] == "user" else "Ассистент"
        text = " ".join((item["content"] or "").strip().split())
        if text:
            lines.append(f"{role}: {text[:700]}")
    return "\n".join(lines)


def _last_assistant_snippet(history: list[dict]) -> str:
    for item in reversed(history):
        if item["role"] == "assistant":
            return (item["content"] or "").strip()[:400]
    return ""


def _profile_text(user) -> str:
    if not user:
        return ""
    parts = [
        f"Имя: {user.name}",
        f"Возраст: {user.age or '—'}",
        f"Сфера: {user.role}",
        f"Опыт в сфере: {user.experience_years if user.experience_years is not None else 0} лет",
    ]
    if user.experience_text:
        parts.append(f"Навыки: {user.experience_text[:400]}")
    return "\n".join(parts)


ROAST_JSON_PROMPT = """Ты личный помощник Kangaroo. Этап: честный разбор стартап-идеи.

Правила:
- Русский, без эмодзи, без воды и вопросов в конце.
- Оценивай справедливо, не занижай всё подряд: слабая 0–45, нормальная 46–65, сильная 66–82, отличная 83+.
- Прожарка жёсткая, но конструктивная: что усилить, где деньги, какой MVP — не только критика.
- Если идея слабая или средняя — дай 2–3 alternatives: каждая отдельная стартап-идея в 1–2 предложениях (сегмент, продукт, монетизация). Альтернативы должны быть реально сильнее исходной — конкретные, а не абстрактные.
- Если идея уже сильная — alternatives: [] или одна улучшенная версия.
- В reply не пиши «всё говно» без аргументов.

Верни JSON:
{
  "reply": "текст прожарки, 2-4 абзаца",
  "score": 0-100,
  "verdict": "вердикт одной фразой (слабая / нормальная / сильная / отличная)",
  "risks": ["риск1", "риск2"],
  "alternatives": ["полное описание альтернативы 1", "полное описание альтернативы 2"],
  "idea_name": "название проекта до 60 символов",
  "idea_tagline": "суть до 120 символов",
  "can_validate": true/false
}

can_validate=true если score >= 48 или идея запускаема после доработок."""


GENERATE_ROADMAP_PROMPT = """Ты личный помощник Kangaroo. Составь персональную вертикальную карту пути фаундера к деньгам.

Правила:
- Русский, без эмодзи.
- Ровно 8–12 шагов, каждый — конкретное действие под ЭТУ идею (не общие фразы).
- Учитывай сферу, опыт, риски и переписку.
- Шаги по порядку: опрос идеи в ленте → pre-MVP преза → питч на проверку → финмодель B2B/B2C → MVP → первые клиенты → масштаб → юрлицо (если нужно для РК) → деньги.
- Последний шаг ОБЯЗАТЕЛЬНО: label «Получение денег», key «money».
- hint — измеримый критерий «шаг сделан» (цифры, факты).
- xp: 30–120 на шаг, на финале 150–250.

Верни JSON:
{
  "steps": [
    {"key": "slug_latin", "label": "короткое название шага до 70 символов", "hint": "критерий выполнения", "xp": 50}
  ],
  "summary": "одно предложение — суть пути для этого проекта"
}"""


ROADMAP_JSON_PROMPT = """Ты опытный ментор Kangaroo. Фаундер идёт по карте к деньгам.

Проект: {startup_name} — {startup_tagline}

Карта шагов:
{steps_outline}

Активный шаг {step_index} из {step_total}: {step_label}
Критерий закрытия: {step_hint}

Как отвечать (обязательно):
1. Сначала ответь на ПОСЛЕДНЕЕ сообщение пользователя — по сути, с конкретикой, примерами, цифрами где уместно. На вопрос — дай развёрнутый ответ, не отмахивайся.
2. Не повторяй дословно свой прошлый ответ из переписки.
3. Не залипай на одной фразе вроде «продолжай MVP» — каждый ответ должен быть новым и полезным.
4. В конце — максимум одно короткое предложение, как это связано с текущим шагом (если уместно).
5. Русский, без эмодзи. reply: 2–6 предложений или до 4 пунктов списком.

step_complete=true только если пользователь явно сообщил факт выполнения критерия (релиз, клиенты, оплата, регистрация). Вопросы, «подробнее», обсуждение — не повод закрывать шаг.
Никогда не закрывай шаг автоматически — фаундер отправляет отчёт через форму в AI-чате (AI + админ).

Верни JSON:
{{
  "reply": "полезный ответ пользователю",
  "step_complete": true/false
}}"""


CHAT_CONTEXT_PROMPT = """Ты личный помощник Kangaroo. Фаундер пишет в чат БЕЗ привязки к карте (галочка снизу выключена).

Проект: {startup_name} — {startup_tagline}

Карта прогресса (ветка к деньгам):
{steps_outline}

Официальный активный шаг: {active_index} — «{active_label}»

Правила:
1. Ответь на последнее сообщение по сути — конкретно, полезно, без воды.
2. Не повторяй прошлый ответ ассистента. Русский, без эмодзи. reply: 2–5 предложений.
3. suggest_via_map=true, если вопрос про выполнение пути: MVP, продукт, клиенты, продажи, юрлицо, деньги, тактика по этапам, «что делать дальше» по проекту.
4. suggest_via_map=false для общей прожарки идеи, эмоций, смены темы, абстрактного brainstorm без привязки к шагам.
5. map_hint — одно короткое предложение: пригласи включить галочку «По карте прогресса» снизу, чтобы ответить по нужному шагу ветки. Только если suggest_via_map=true.

Верни JSON:
{{
  "reply": "ответ",
  "suggest_via_map": false,
  "map_hint": ""
}}"""


ROADMAP_SMART_PROMPT = """Ты ментор Kangaroo. Фаундер задал вопрос в контексте карты прогресса к деньгам.

Проект: {startup_name} — {startup_tagline}

Карта шагов (индекс с 0):
{steps_outline}

Официальный активный шаг сейчас: {active_index} — «{active_label}»
Критерий закрытия активного шага: {active_hint}

Задача:
1. Определи focus_step_index (0..{max_index}) — к какому шагу карты относится вопрос пользователя. Обычно это активный шаг, но может быть другой, если вопрос про прошлый/будущий этап.
2. Ответь на последнее сообщение конкретно и полезно, в контексте выбранного шага. Не повторяй прошлый ответ ассистента.
3. Русский, без эмодзи. reply: 2–6 предложений или до 4 пунктов.
4. Если пользователь пишет что сделал/выполнил/готово («сделал то что просил», «готово», «выполнил»), но без чётких фактов по критерию:
   — в reply спроси: «Хотите отметить это на карте прогресса?»
   — ask_map_confirm: true, step_complete: false
5. step_complete=true только если пользователь подтверждает отметку на карте (да, отметь, добавь на карту) ИЛИ дал явные факты выполнения критерия активного шага ({active_index}).
6. step_complete всегда false в ответе — закрытие шага только через форму «Отчёт на проверку» в AI-чате (AI + админ).
7. Вопросы и обсуждение без отчёта о выполнении — ask_map_confirm: false.

Верни JSON:
{{
  "focus_step_index": 0,
  "reply": "ответ",
  "step_complete": false,
  "ask_map_confirm": false
}}"""


ROADMAP_COMPLETED_PROMPT = """Ты ментор Kangaroo. Ветка к деньгам для «{startup_name}» пройдена.

Выполненные шаги:
{steps_outline}

Отвечай на последнее сообщение пользователя конкретно и по делу. Не повторяй прошлый ответ. Русский, без эмодзи, 2–6 предложений.

Верни JSON:
{{
  "reply": "содержательный ответ"
}}"""


def generate_roast(history: list[dict], user) -> dict[str, Any]:
    payload = _history_text(history)
    profile = _profile_text(user)
    user_block = f"Профиль фаундера:\n{profile}\n\nПереписка:\n{payload}" if profile else payload
    data = _json_chat(ROAST_JSON_PROMPT, user_block)
    data.setdefault("reply", "Недостаточно данных для разбора.")
    data.setdefault("score", 40)
    data.setdefault("verdict", "Требует доработки")
    data.setdefault("risks", [])
    data.setdefault("alternatives", [])
    data.setdefault("idea_name", "Новый проект")
    data.setdefault("idea_tagline", "Стартап-идея из чата")
    data.setdefault("can_validate", bool(data.get("score", 0) >= 48))
    return data


def generate_roadmap_steps(
    history: list[dict],
    user,
    idea_name: str,
    idea_tagline: str,
    risks: list[str] | None = None,
) -> dict[str, Any]:
    profile = _profile_text(user)
    payload = _history_text(history)
    risks_block = ""
    if risks:
        risks_block = "Риски из прожарки:\n" + "\n".join(f"- {r}" for r in risks[:6])
    user_block = (
        f"Проект: {idea_name}\n"
        f"Суть: {idea_tagline}\n"
        f"{risks_block}\n"
        f"Профиль:\n{profile}\n\n"
        f"Переписка:\n{payload}"
    )
    data = _json_chat(GENERATE_ROADMAP_PROMPT, user_block, max_tokens=1100)
    raw_steps = data.get("steps", [])
    steps = normalize_steps(raw_steps if isinstance(raw_steps, list) else [])
    data["steps"] = steps
    data.setdefault("summary", f"Персональный путь из {len(steps)} шагов к деньгам.")
    return data


def generate_context_turn(
    history: list[dict],
    user,
    startup_name: str,
    steps: list[dict[str, Any]],
    active_step_index: int,
    startup_tagline: str = "",
) -> dict[str, Any]:
    active_step_index = max(0, min(active_step_index, len(steps) - 1))
    active = steps[active_step_index]
    steps_outline = "\n".join(f"{i + 1}. {s['label']}" for i, s in enumerate(steps))
    system = CHAT_CONTEXT_PROMPT.format(
        startup_name=startup_name,
        startup_tagline=startup_tagline or "стартап",
        steps_outline=steps_outline,
        active_index=active_step_index + 1,
        active_label=active["label"],
    )
    profile = _profile_text(user)
    payload = _history_text(history)
    last_reply = _last_assistant_snippet(history)
    avoid = f"\nТвой прошлый ответ (не повторяй): {last_reply}\n" if last_reply else ""
    user_block = f"Проект: {startup_name}\n{profile}{avoid}\n\nПереписка:\n{payload}"
    data = _json_chat(system, user_block, max_tokens=700, temperature=0.65)
    data.setdefault("reply", "Напиши подробнее — разберём.")
    data.setdefault("suggest_via_map", False)
    data.setdefault("map_hint", "")
    if not data.get("suggest_via_map"):
        data["map_hint"] = ""
    return data


def generate_roadmap_smart_turn(
    history: list[dict],
    user,
    startup_name: str,
    steps: list[dict[str, Any]],
    active_step_index: int,
    startup_tagline: str = "",
) -> dict[str, Any]:
    active_step_index = max(0, min(active_step_index, len(steps) - 1))
    active = steps[active_step_index]
    steps_outline = "\n".join(
        f"{i}. [{i}] {s['label']} — {s.get('hint', '')}" for i, s in enumerate(steps)
    )
    system = ROADMAP_SMART_PROMPT.format(
        startup_name=startup_name,
        startup_tagline=startup_tagline or "стартап",
        steps_outline=steps_outline,
        active_index=active_step_index,
        active_label=active["label"],
        active_hint=active.get("hint", ""),
        max_index=len(steps) - 1,
    )
    profile = _profile_text(user)
    payload = _history_text(history)
    last_reply = _last_assistant_snippet(history)
    avoid = f"\nТвой прошлый ответ (не повторяй): {last_reply}\n" if last_reply else ""
    user_block = (
        f"Проект: {startup_name}\n"
        f"Суть: {startup_tagline}\n"
        f"{profile}{avoid}\n\n"
        f"Переписка:\n{payload}"
    )
    data = _json_chat(system, user_block, max_tokens=800, temperature=0.7)
    try:
        focus = int(data.get("focus_step_index", active_step_index))
    except (TypeError, ValueError):
        focus = active_step_index
    data["focus_step_index"] = max(0, min(focus, len(steps) - 1))
    data.setdefault("reply", "Уточни вопрос — отвечу по карте прогресса.")
    data.setdefault("step_complete", False)
    data.setdefault("ask_map_confirm", False)
    data["step_complete"] = False
    return data


def generate_roadmap_turn(
    history: list[dict],
    user,
    step_index: int,
    startup_name: str,
    steps: list[dict[str, Any]],
    startup_tagline: str = "",
) -> dict[str, Any]:
    if step_index >= len(steps):
        step_index = len(steps) - 1
    step = steps[step_index]
    steps_outline = "\n".join(f"{i + 1}. {s['label']}" for i, s in enumerate(steps))
    system = ROADMAP_JSON_PROMPT.format(
        startup_name=startup_name,
        startup_tagline=startup_tagline or "стартап",
        step_label=step["label"],
        step_hint=step.get("hint", ""),
        step_index=step_index + 1,
        step_total=len(steps),
        steps_outline=steps_outline,
    )
    profile = _profile_text(user)
    payload = _history_text(history)
    last_reply = _last_assistant_snippet(history)
    avoid = f"\nТвой прошлый ответ (не повторяй): {last_reply}\n" if last_reply else ""
    user_block = (
        f"Проект: {startup_name}\n"
        f"Суть: {startup_tagline}\n"
        f"Активный шаг: {step['label']}\n"
        f"Критерий: {step.get('hint', '')}\n"
        f"{profile}{avoid}\n\n"
        f"Переписка:\n{payload}"
    )
    data = _json_chat(system, user_block, max_tokens=750, temperature=0.7)
    data.setdefault("reply", "Расскажи подробнее — отвечу по твоему вопросу.")
    data.setdefault("step_complete", False)
    data["step_complete"] = False
    return data


def generate_roadmap_completed_turn(
    history: list[dict],
    user,
    startup_name: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    steps_outline = "\n".join(f"{i + 1}. {s['label']}" for i, s in enumerate(steps))
    system = ROADMAP_COMPLETED_PROMPT.format(
        startup_name=startup_name,
        steps_outline=steps_outline,
    )
    profile = _profile_text(user)
    payload = _history_text(history)
    last_reply = _last_assistant_snippet(history)
    avoid = f"\nТвой прошлый ответ (не повторяй): {last_reply}\n" if last_reply else ""
    user_block = f"Проект: {startup_name}\nВетка завершена.\n{profile}{avoid}\n\nПереписка:\n{payload}"
    data = _json_chat(system, user_block, max_tokens=750, temperature=0.7)
    data.setdefault("reply", "Ветка пройдена — продолжай масштабировать проект.")
    data["step_complete"] = False
    return data


STEP_COACH_PROMPT = """Ты ментор Kangaroo на конкретном шаге roadmap.

Проект: {startup_name} — {startup_tagline}
Шаг {step_index} из {step_total}: {step_label}
Критерий: {step_hint}
Weekly goals: {weekly_goals}

Инструкция для этого уровня:
{step_specific_coach}

Дай практичный совет фаундеру. Русский, без эмодзи.

Верни JSON: {{"reply": "текст"}}"""


STEP_VALIDATE_PROMPT = """Ты строгий валидатор шагов Kangaroo. Двухэтапная проверка: сначала ты, потом админ.

Проект: {startup_name} — {startup_tagline}
Текущий шаг {step_index} из {step_total}: {step_label}
Критерий закрытия: {step_hint}

Предыдущий этап (обязательно проверь):
{previous_step_summary}

Инструкция валидации для этого уровня:
{step_specific_validation}

Отчёт фаундера:
{report}

Доказательство (ссылка): {evidence_url}

{validation_json}"""


ONE_PAGER_PROMPT = """Сгенерируй one-pager для инвестора по стартапу.

Проект: {startup_name}
Tagline: {startup_tagline}
Стадия: {stage}
Traction: {traction}
Roadmap: {steps_outline}

Верни JSON:
{{
  "title": "название",
  "problem": "проблема 2-3 предложения",
  "solution": "решение",
  "market": "рынок KZ/CIS",
  "traction": "текущие метрики",
  "business_model": "монетизация",
  "team": "команда",
  "ask": "что ищет фаундер"
}}"""


PITCH_PROMPT = """Сгенерируй outline питч-дека из 10 слайдов.

Проект: {startup_name} — {startup_tagline}
Roadmap progress: {progress}

Верни JSON:
{{
  "slides": [
    {{"num": 1, "title": "...", "bullets": ["...", "..."]}}
  ]
}}"""


PITCH_PRE_PROMPT = """Сгенерируй PRE-MVP питч-дек (ещё нет продукта и traction).

Проект: {startup_name} — {startup_tagline}
Стадия: {stage}

Правила: 7 слайдов, без выдуманных метрик и fake traction. Фокус на гипотезе.

Верни JSON:
{{
  "stage": "pre_mvp",
  "slides": [
    {{"num": 1, "title": "Problem", "bullets": ["..."]}}
  ]
}}"""


PITCH_VALIDATED_PROMPT = """Сгенерируй VALIDATED питч-дек (есть MVP/traction для проверки).

Проект: {startup_name} — {startup_tagline}
Прогресс roadmap: {progress}
Traction score: {traction}

Правила: 10 слайдов, обязательны метрики, traction, unit economics если есть.

Верни JSON:
{{
  "stage": "validated",
  "slides": [
    {{"num": 1, "title": "...", "bullets": ["..."]}}
  ]
}}"""


PITCH_ANALYZE_PROMPT = """Ты инвестор-аналитик Kangaroo. Разбери питч стартапа.

Проект: {startup_name} — {startup_tagline}

Текст питча:
{pitch_text}

Верни JSON:
{{
  "score": 0-100,
  "verdict": "слабый / нормальный / сильный",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "slides_feedback": [{{"slide": "название", "issue": "...", "fix": "..."}}],
  "investor_ready": true/false,
  "summary": "2-3 предложения для фаундера"
}}

score >= 60 если питч готов к показу инвестору с доработками."""


FIN_MODEL_PROMPT = """Ты финансовый ментор Kangaroo. Проверь и дополни финмодель.

Проект: {startup_name} — {startup_tagline}
Тип модели: {model_type} ({model_label})

Данные фаундера:
{inputs}

Для B2B проверь: ACV, sales cycle, gross margin, churn, CAC payback.
Для B2C проверь: CAC, ARPU, retention, LTV, LTV/CAC.

Верни JSON:
{{
  "score": 0-100,
  "model_type": "b2b" или "b2c",
  "verdict": "краткий вердикт",
  "metrics": {{"key": "value с пояснением"}},
  "gaps": ["чего не хватает"],
  "recommendations": ["что улучшить"],
  "summary": "2-3 предложения"
}}"""


def generate_step_coach_turn(
    user,
    startup_name: str,
    startup_tagline: str,
    step: dict,
    step_index: int,
    step_total: int,
    weekly_goals: list[str] | None = None,
) -> dict[str, Any]:
    goals_text = ", ".join(weekly_goals or []) or "—"
    step_key = infer_step_key(step)
    system = STEP_COACH_PROMPT.format(
        startup_name=startup_name,
        startup_tagline=startup_tagline or "стартап",
        step_index=step_index + 1,
        step_total=step_total,
        step_label=step["label"],
        step_hint=step.get("hint", ""),
        weekly_goals=goals_text,
        step_specific_coach=step_prompt_for(step_key, "coach"),
    )
    profile = _profile_text(user)
    data = _json_chat(system, f"Профиль:\n{profile}\n\nДай совет по текущему шагу.", max_tokens=500)
    data.setdefault("reply", "Сфокусируйся на измеримом результате по критерию шага.")
    return data


def validate_step_report(
    user,
    startup,
    step: dict,
    step_index: int,
    step_total: int,
    *,
    report: str,
    evidence_url: str | None,
    previous_step_summary: str,
) -> dict[str, Any]:
    step_key = infer_step_key(step)
    system = STEP_VALIDATE_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline or "стартап",
        step_index=step_index + 1,
        step_total=step_total,
        step_label=step["label"],
        step_hint=step.get("hint", ""),
        previous_step_summary=previous_step_summary or "—",
        step_specific_validation=step_prompt_for(step_key, "validation"),
        report=report.strip()[:500],
        evidence_url=evidence_url or "не указана",
        validation_json=STEP_VALIDATION_JSON,
    )
    profile = _profile_text(user)
    data = _json_chat(system, f"Профиль фаундера:\n{profile}", max_tokens=650, temperature=0.35)
    data.setdefault("approved", False)
    data.setdefault("previous_step_ok", False)
    data.setdefault("confidence", 0)
    data.setdefault("feedback", "Недостаточно данных для подтверждения шага.")
    data.setdefault("missing_criteria", [])
    data.setdefault("admin_summary", "")
    return data


def generate_one_pager(user, startup, steps: list[dict], progress: dict) -> dict[str, Any]:
    steps_outline = "\n".join(f"{i + 1}. {s['label']}" for i, s in enumerate(steps))
    system = ONE_PAGER_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline,
        stage=startup.stage,
        traction=startup.traction,
        steps_outline=steps_outline,
    )
    profile = _profile_text(user)
    data = _json_chat(system, profile, max_tokens=900)
    data.setdefault("title", startup.name)
    for key in ("problem", "solution", "market", "traction", "business_model", "team", "ask"):
        data.setdefault(key, "—")
    return data


def generate_pitch_outline(user, startup, steps: list[dict], progress: dict) -> dict[str, Any]:
    if progress.get("done", 0) >= 4:
        return generate_pitch_validated(user, startup, steps, progress)
    return generate_pitch_pre(user, startup, steps, progress)


def generate_pitch_pre(user, startup, steps: list[dict], progress: dict) -> dict[str, Any]:
    system = PITCH_PRE_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline,
        stage=startup.stage,
    )
    profile = _profile_text(user)
    data = _json_chat(system, profile, max_tokens=1100)
    data.setdefault("slides", [])
    data.setdefault("stage", "pre_mvp")
    return data


def generate_pitch_validated(user, startup, steps: list[dict], progress: dict) -> dict[str, Any]:
    system = PITCH_VALIDATED_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline,
        progress=f"{progress.get('percent', 0)}% ({progress.get('done', 0)}/{progress.get('total', 0)} шагов)",
        traction=startup.traction,
    )
    profile = _profile_text(user)
    data = _json_chat(system, profile, max_tokens=1300)
    data.setdefault("slides", [])
    data.setdefault("stage", "validated")
    return data


def analyze_pitch_text(user, startup, pitch_text: str) -> dict[str, Any]:
    system = PITCH_ANALYZE_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline,
        pitch_text=pitch_text.strip()[:6000],
    )
    profile = _profile_text(user)
    data = _json_chat(system, profile, max_tokens=900, temperature=0.4)
    data.setdefault("score", 0)
    data.setdefault("verdict", "слабый")
    data.setdefault("strengths", [])
    data.setdefault("weaknesses", [])
    data.setdefault("slides_feedback", [])
    data.setdefault("investor_ready", False)
    data.setdefault("summary", "")
    return data


def analyze_fin_model(user, startup, model_type: str, inputs: dict[str, str]) -> dict[str, Any]:
    model_type = (model_type or "b2c").lower()
    if model_type not in {"b2b", "b2c"}:
        model_type = "b2c"
    model_label = "B2B — продажи компаниям" if model_type == "b2b" else "B2C — продажи людям"
    lines = "\n".join(f"{k}: {v}" for k, v in inputs.items() if v)
    system = FIN_MODEL_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline,
        model_type=model_type,
        model_label=model_label,
        inputs=lines or "—",
    )
    profile = _profile_text(user)
    data = _json_chat(system, profile, max_tokens=900, temperature=0.4)
    data.setdefault("score", 0)
    data.setdefault("model_type", model_type)
    data.setdefault("metrics", {})
    data.setdefault("gaps", [])
    data.setdefault("recommendations", [])
    data.setdefault("summary", "")
    return data
