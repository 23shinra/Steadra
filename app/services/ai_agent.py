import json
from typing import Any

from flask import current_app
from openai import OpenAI

from .roadmap import ROADMAP_STEPS, normalize_steps
from .startup_audit import (
    audit_rubric_for_prompt,
    normalize_criteria,
    score_from_criteria,
    verdict_from_score,
)
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


ROAST_JSON_PROMPT = """Ты личный помощник Kangaroo. Этап: разбор стартап-идеи.

Сначала реши: хватает ли данных для честной оценки по 10 блокам аудита.

needs_clarify=true (БЕЗ оценки), если идея сухая/общая — мало конкретики. Примеры:
«хочу продавать кроссовки», «сделать приложение», «AI для бизнеса», одна фраза без сегмента/модели/как зарабатывать.
Тогда: как план в Cursor — короткий reply (1 абзац) + 2–4 точных вопроса. Не оценивай, не ставь criteria.
Вопросы про: кому продаёт, какую боль закрывает, как зарабатывает, чем отличается, что уже есть (MVP/клиенты/деньги).

needs_clarify=false — когда есть сегмент + продукт/оффер + хоть намёк на монетизацию ИЛИ пользователь уже ответил на уточнения.
Тогда делай полную прожарку:
- Русский, без эмодзи, без воды.
- Выставь criteria (все 10 блоков). Итоговый score модель НЕ считает.
- Если идея слабая/средняя — 2–3 alternatives (сегмент, продукт, монетизация).
- reply: 2–3 коротких абзаца по слабым блокам. Не пересказывай все 10 блоков.
- Если в переписке ассистент уже задавал уточнения — больше не уточняй, оценивай по ответам.

{audit_rubric}

Если needs_clarify=true, верни JSON:
{{
  "needs_clarify": true,
  "reply": "1 абзац: что понял и зачем уточняешь",
  "plan_title": "Уточним идею",
  "questions": ["вопрос 1", "вопрос 2", "вопрос 3"]
}}

Если needs_clarify=false, верни JSON:
{{
  "needs_clarify": false,
  "reply": "текст прожарки, 2-3 абзаца",
  "verdict": "Слабая идея / Неплохо / Сильная идея / Отличная идея",
  "criteria": [
    {{"id": "basis", "score": 0, "note": "кратко"}},
    {{"id": "custdev", "score": 0, "note": "кратко"}},
    {{"id": "market", "score": 0, "note": "кратко"}},
    {{"id": "product", "score": 0, "note": "кратко"}},
    {{"id": "acquisition", "score": 0, "note": "кратко"}},
    {{"id": "monetization", "score": 0, "note": "кратко"}},
    {{"id": "unit_econ", "score": 0, "note": "кратко"}},
    {{"id": "retention", "score": 0, "note": "кратко"}},
    {{"id": "moat", "score": 0, "note": "кратко"}},
    {{"id": "team_finance", "score": 0, "note": "кратко"}}
  ],
  "risks": ["риск1", "риск2"],
  "alternatives": ["альтернатива 1", "альтернатива 2"],
  "idea_name": "название до 60 символов",
  "idea_tagline": "суть до 120 символов",
  "can_validate": true/false
}}

can_validate=true если идея запускаема после доработок (средний score блоков ≥2.4)."""


ROAST_FORCE_PROMPT_SUFFIX = """

ВАЖНО: пользователь просит оценить сейчас / данных уже достаточно.
needs_clarify=false. Сразу полная оценка по criteria, без новых уточняющих вопросов."""


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



GENERATE_STEP_BRANCHES_PROMPT = """Ты личный помощник Kangaroo. Основная карта прогресса уже зафиксирована — её шаги менять нельзя.

Проект: {startup_name} — {startup_tagline}

Основные шаги карты (только контекст, labels и hints не переписывай):
{steps_outline}

Задача: для КАЖДОГО шага (индекс 0..{max_index}) придумай ровно 3 промежуточных подшага — конкретные действия под ЭТУ тему и тип бизнеса.
- Названия подшагов уникальны для проекта: производство, приложение, услуга, offline, B2B — отталкивайся от сути «{startup_tagline}».
- Не используй одни и те же формулировки для всех проектов.
- Подшаги — логическая дорожка внутри родительского шага, ведут к его критерию закрытия.
- Коротко: до 70 символов, русский, без эмодзи, без воды.

Верни JSON:
{{
  "branches": {{
    "0": [{{"label": "..."}}, {{"label": "..."}}, {{"label": "..."}}],
    "1": [...],
    ...
  }}
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


ROADMAP_SMART_PROMPT = """Ты ментор Kangaroo. Фаундер пишет в чате; галочка «По карте» включена, но это НЕ значит, что каждый ответ должен быть про текущий шаг.

Проект: {startup_name} — {startup_tagline}

Карта шагов (индекс с 0):
{steps_outline}

Официальный активный шаг сейчас: {active_index} — «{active_label}»
Критерий закрытия активного шага: {active_hint}

Сначала классифицируй ПОСЛЕДНЕЕ сообщение пользователя:
- off_topic=true — small talk / не про проект и не про шаги: «как дела», шутки, личное, настроение, общие вопросы, смена темы без запроса по этапу.
- off_topic=false — про проект, презу, клиентов, метрики, что делать дальше, отчёт по шагу, карту.

Если off_topic=true:
1. Ответь по-человечески: коротко, живо, по делу на его фразу. Можно одной шуткой или тёплым тоном.
2. НЕ вставляй шаблон про активный шаг, критерии, «собери отзывы», «продолжай MVP», «по карте прогресса».
3. focus_step_index = {active_index}. ask_map_confirm=false. step_complete=false.
4. reply: 1–3 предложения.

Если off_topic=false:
1. focus_step_index (0..{max_index}) — к какому шагу относится вопрос (часто активный, но может быть другой).
2. Ответь конкретно и полезно. Не повторяй прошлый ответ ассистента.
3. Русский, без эмодзи. reply: 2–6 предложений или до 4 пунктов.
4. Если пишет «сделал/готово/выполнил» без фактов по критерию:
   — спроси: «Хотите отметить это на карте прогресса?»
   — ask_map_confirm: true
5. step_complete всегда false — закрытие шага только через форму «Отчёт на проверку».

Верни JSON:
{{
  "off_topic": false,
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



def generate_roast(history: list[dict], user, *, force_score: bool = False) -> dict[str, Any]:
    payload = _history_text(history)
    profile = _profile_text(user)
    user_block = f"Профиль фаундера:\n{profile}\n\nПереписка:\n{payload}" if profile else payload
    system = ROAST_JSON_PROMPT.format(audit_rubric=audit_rubric_for_prompt())
    if force_score:
        system = system + ROAST_FORCE_PROMPT_SUFFIX
    data = _json_chat(system, user_block, max_tokens=720, temperature=0.4)
    data.setdefault("reply", "Недостаточно данных для разбора.")
    needs_clarify = bool(data.get("needs_clarify")) and not force_score
    if needs_clarify:
        questions = data.get("questions") or []
        if not isinstance(questions, list):
            questions = []
        questions = [" ".join(str(q).split())[:160] for q in questions if str(q).strip()][:4]
        if questions:
            return {
                "needs_clarify": True,
                "reply": data.get("reply") or "Давай уточним идею, прежде чем ставить оценку.",
                "plan_title": (" ".join(str(data.get("plan_title") or "Уточним идею").split()))[:80],
                "questions": questions,
                "score": None,
                "criteria": [],
                "risks": [],
                "alternatives": [],
                "can_validate": False,
            }

    criteria = normalize_criteria(data.get("criteria"))
    score = score_from_criteria(criteria)
    data["needs_clarify"] = False
    data["criteria"] = criteria
    data["score"] = score
    data["verdict"] = verdict_from_score(score)
    data.setdefault("risks", [])
    data.setdefault("alternatives", [])
    data.setdefault("idea_name", "Новый проект")
    data.setdefault("idea_tagline", "Стартап-идея из чата")
    avg = sum(int(c["score"]) for c in criteria) / max(len(criteria), 1)
    if "can_validate" not in data:
        data["can_validate"] = bool(score >= 48 or avg >= 2.4)
    else:
        data["can_validate"] = bool(data.get("can_validate"))
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


def generate_step_branches(
    history: list[dict],
    user,
    startup_name: str,
    startup_tagline: str,
    steps: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    from .step_branches import ensure_branch_keys

    if not steps:
        return {}
    steps_outline = "\n".join(
        f"{i}. [{i}] {s['label']} — {s.get('hint', '')}" for i, s in enumerate(steps)
    )
    profile = _profile_text(user)
    payload = _history_text(history)
    user_block = (
        f"Проект: {startup_name}\n"
        f"Суть: {startup_tagline}\n"
        f"Профиль:\n{profile}\n\n"
        f"Переписка:\n{payload}"
    )
    system = GENERATE_STEP_BRANCHES_PROMPT.format(
        startup_name=startup_name,
        startup_tagline=startup_tagline or "стартап",
        steps_outline=steps_outline,
        max_index=len(steps) - 1,
    )
    try:
        data = _json_chat(system, user_block, max_tokens=1400, temperature=0.55)
    except Exception:
        return {}
    raw = data.get("branches", {})
    if not isinstance(raw, dict):
        return {}
    return ensure_branch_keys(steps, raw)


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
    data.setdefault("reply", "Напиши подробнее — разберём.")
    data.setdefault("step_complete", False)
    data.setdefault("ask_map_confirm", False)
    data.setdefault("off_topic", False)
    data["step_complete"] = False
    if data.get("off_topic"):
        data["ask_map_confirm"] = False
        data["focus_step_index"] = active_step_index
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

Чеклист отправной точки (100-вопросная валидация):
{milestone_questions}

Отчёт фаундера:
{report}

Ссылку или файл proof пользователь не прикладывает — оцени только текст отчёта.
Не требуй proof-ссылку и не отклоняй отчёт только из‑за её отсутствия.

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


PITCH_ANALYZE_PROMPT = """Ты инвестор-аналитик Kangaroo. Разбери ПРЕЗЕНТАЦИЮ по слайдам.

Проект: {startup_name} — {startup_tagline}

Правила:
- Русский, без эмодзи, без воды.
- Оцени КАЖДЫЙ слайд 0–5 (0=пусто/вредно, 3=норм, 5=инвестор ок).
- Прямо называй плохие слайды: что не так и как переписать.
- Не выдумывай факты, которых нет на слайдах.
- Итоговый score 0–100 модель НЕ считает — его соберёт сервер из баллов слайдов.
- verdict: слабый / нормальный / сильный.

{previous_block}

Слайды:
{slides_block}

Верни JSON:
{{
  "verdict": "слабый / нормальный / сильный",
  "summary": "2-3 предложения",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "slides": [
    {{"num": 1, "title": "как на слайде", "score": 0, "verdict": "слабый", "issue": "что плохо/чего нет", "fix": "конкретная правка"}}
  ],
  "investor_ready": true/false
}}

investor_ready=true только если среднее по слайдам ≥ 3.2 и нет критичных дыр (проблема, рынок, как зарабатываем, ask)."""


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
    from .validation_questions import validation_prompt_block

    step_key = infer_step_key(step)
    milestone_block = validation_prompt_block(step_key) or "Для этого шага отдельный чеклист отправной точки не задан."
    system = STEP_VALIDATE_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline or "стартап",
        step_index=step_index + 1,
        step_total=step_total,
        step_label=step["label"],
        step_hint=step.get("hint", ""),
        previous_step_summary=previous_step_summary or "—",
        step_specific_validation=step_prompt_for(step_key, "validation"),
        milestone_questions=milestone_block,
        report=report.strip()[:500],
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


def analyze_pitch_text(user, startup, pitch_text: str, previous: dict | None = None) -> dict[str, Any]:
    from .pitch_deck import extract_pasted_text

    return analyze_pitch_deck(user, startup, extract_pasted_text(pitch_text), previous=previous, source="text")


def _pitch_previous_block(previous: dict | None) -> str:
    if not previous or previous.get("score") is None:
        return "Это первая проверка дека. Оцени как есть."
    lines = [
        "Это ПЕРЕПРОВЕРКА. Сравни с прошлым разбором, не копируй его.",
        f"Прошлый score: {previous.get('score')}/100 · {previous.get('verdict') or '—'}.",
    ]
    old_slides = previous.get("slides") or []
    if old_slides:
        lines.append("Прошлые слайды:")
        for s in old_slides[:16]:
            lines.append(
                f"- #{s.get('num')}: {s.get('title') or '—'} · {s.get('score', '—')}/5 · {s.get('issue') or ''}"
            )
    lines.append("В delta укажи, что стало лучше/хуже. Не завышай score без реальных правок в тексте слайдов.")
    return "\n".join(lines)


def analyze_pitch_deck(
    user,
    startup,
    slides: list[dict[str, Any]],
    *,
    previous: dict | None = None,
    source: str = "upload",
    filename: str = "",
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from .pitch_deck import slides_to_prompt

    if not slides:
        raise ValueError("Нет слайдов для разбора.")
    system = PITCH_ANALYZE_PROMPT.format(
        startup_name=startup.name,
        startup_tagline=startup.tagline or "стартап",
        previous_block=_pitch_previous_block(previous),
        slides_block=slides_to_prompt(slides)[:12000],
    )
    profile = _profile_text(user)
    data = _json_chat(system, profile, max_tokens=1200, temperature=0.3)
    scored = []
    raw_slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    by_num = {}
    for item in raw_slides:
        if not isinstance(item, dict):
            continue
        try:
            num = int(item.get("num") or 0)
        except (TypeError, ValueError):
            continue
        try:
            sc = int(item.get("score", 0))
        except (TypeError, ValueError):
            sc = 0
        by_num[num] = {
            "num": num,
            "title": str(item.get("title") or "")[:80],
            "score": max(0, min(5, sc)),
            "verdict": str(item.get("verdict") or "").strip()[:40],
            "issue": " ".join(str(item.get("issue") or "").split())[:220],
            "fix": " ".join(str(item.get("fix") or "").split())[:220],
        }
    for s in slides:
        row = by_num.get(s["num"]) or {
            "num": s["num"],
            "title": s["title"],
            "score": 0,
            "verdict": "слабый",
            "issue": "Модель не разобрала слайд.",
            "fix": "Добавь ясный заголовок и 3 факта.",
        }
        if not row.get("title"):
            row["title"] = s["title"]
        scored.append(row)
    total = sum(int(s["score"]) for s in scored)
    max_total = 5 * max(len(scored), 1)
    score = int(round(100 * total / max_total)) if max_total else 0
    history = []
    if isinstance(previous, dict):
        history = list(previous.get("history") or [])
        if previous.get("score") is not None:
            history.append(
                {
                    "score": previous.get("score"),
                    "verdict": previous.get("verdict"),
                    "at": previous.get("reviewed_at"),
                    "source": previous.get("source"),
                    "filename": previous.get("filename"),
                }
            )
        history = history[-5:]
    prev_score = previous.get("score") if isinstance(previous, dict) else None
    delta = None if prev_score is None else int(score) - int(prev_score)
    data["slides"] = scored
    data["slides_feedback"] = [
        {"slide": f"Слайд {s['num']}: {s['title']}", "issue": s["issue"], "fix": s["fix"]}
        for s in scored
    ]
    data["score"] = score
    # Verdict and investor flag always follow the numeric score — never trust model wording.
    data["verdict"] = "сильный" if score >= 66 else "нормальный" if score >= 46 else "слабый"
    data.setdefault("strengths", [])
    data.setdefault("weaknesses", [])
    data.setdefault("summary", "")
    data["investor_ready"] = score >= 60
    data["source"] = source
    data["filename"] = (filename or "")[:120]
    data["reviewed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["previous_score"] = prev_score
    data["delta"] = delta
    data["history"] = history
    data["slide_count"] = len(scored)
    return data


IMAGE_CHAT_PROMPT = """Ты ментор Kangaroo. Фаундер прислал фото/скрин по проекту «{startup_name}».
Опиши, что видишь, и дай короткий практичный комментарий для стартапа (что ок / что поправить).
Русский, без эмодзи, 2–5 коротких абзацев или пунктов. Не выдумывай текст, которого нет на фото."""


def describe_chat_image(
    user,
    startup,
    image_bytes: bytes,
    *,
    mime: str = "image/jpeg",
    filename: str = "",
) -> str:
    import base64

    if not image_bytes:
        raise ValueError("Пустое изображение.")
    if len(image_bytes) > 6 * 1024 * 1024:
        raise ValueError("Фото больше 6 МБ.")
    mime = (mime or "image/jpeg").split(";")[0].strip().lower()
    if mime not in {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}:
        mime = "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    system = IMAGE_CHAT_PROMPT.format(startup_name=getattr(startup, "name", None) or "стартап")
    profile = _profile_text(user)
    response = _client().chat.completions.create(
        model=(
            current_app.config.get("OPENAI_VISION_MODEL")
            or current_app.config.get("OPENAI_MODEL")
            or "gpt-4o-mini"
        ),
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Профиль:\n{profile}\n\nФайл: {filename or 'photo'}\nЧто на фото и что делать дальше?",
                    },
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            },
        ],
        max_tokens=500,
        temperature=0.4,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("Пустой ответ от модели по фото.")
    return content


VIDEO_CHAT_PROMPT = """Ты ментор Kangaroo. Фаундер прислал видео по проекту «{startup_name}».

Тебе дали:
1) кадры по таймлайну (это сжатая «версия» ролика — воспринимай как просмотр видео),
2) расшифровку речи с таймкодами (если есть).

Задача: ответь так, будто ты реально посмотрел ролик целиком.
Структура ответа (коротко, по делу, русский, без эмодзи):
- О чём видео (1–2 предложения)
- Что видно / что говорят (факты)
- Сильные стороны для стартапа
- Слабые места / риски
- Что сделать дальше (3 конкретных шага)

Правила:
- Опирайся на кадры + речь. Не выдумывай метрики и факты.
- Если речи нет — разбирай по картинке и динамике кадров.
- Пиши уверенно и полезно, без оговорок «я видел только кадры»."""


def describe_chat_video(
    user,
    startup,
    *,
    frames_b64: list[str] | None = None,
    frames: list[dict] | None = None,
    transcript: str | None = None,
    duration: float | None = None,
    filename: str = "",
    has_speech: bool = False,
) -> str:
    frame_rows: list[dict] = []
    if frames:
        for item in frames:
            if not isinstance(item, dict) or not item.get("b64"):
                continue
            frame_rows.append({"t": item.get("t"), "b64": item["b64"]})
    elif frames_b64:
        frame_rows = [{"t": None, "b64": b64} for b64 in frames_b64]
    if not frame_rows:
        raise ValueError("Нет кадров для разбора.")

    system = VIDEO_CHAT_PROMPT.format(startup_name=getattr(startup, "name", None) or "стартап")
    profile = _profile_text(user)
    timeline = []
    for i, row in enumerate(frame_rows[:14], 1):
        mark = f"{row['t']:.1f}с" if isinstance(row.get("t"), (int, float)) else f"#{i}"
        timeline.append(mark)
    speech_block = (transcript or "").strip()
    if not speech_block:
        speech_block = "Речи почти нет / тишина — опирайся на визуал."
    parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Профиль фаундера:\n{profile}\n\n"
                f"Видео: {filename or 'clip'}\n"
                f"Длительность: {duration or '—'} сек\n"
                f"Кадры по времени: {', '.join(timeline)}\n"
                f"Есть речь: {'да' if has_speech or bool(transcript) else 'нет'}\n\n"
                f"Расшифровка:\n{speech_block}\n\n"
                "Дальше идут кадры строго по порядку времени. Смотри как ролик."
            ),
        }
    ]
    total = len(frame_rows[:14])
    for i, row in enumerate(frame_rows[:14]):
        # High detail on ends + middle for better product/UI reading; low on the rest.
        detail = "high" if i in {0, total // 2, total - 1} or total <= 8 else "low"
        t = row.get("t")
        label = f"Кадр {i + 1}" + (f" · {t:.1f}с" if isinstance(t, (int, float)) else "")
        parts.append({"type": "text", "text": label})
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{row['b64']}", "detail": detail},
            }
        )
    # Prefer a stronger vision model if configured separately; else main chat model.
    model = (
        current_app.config.get("OPENAI_VISION_MODEL")
        or current_app.config.get("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    response = _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": parts},
        ],
        max_tokens=900,
        temperature=0.3,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("Пустой ответ от модели по видео.")
    return content


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
