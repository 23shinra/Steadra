import json
from typing import Any

ROADMAP_STEPS = [
    {"key": "idea_poll", "label": "Опросник идеи", "hint": "Отчёт в чате → опрос в ленте в течение 24 ч → ≥3 голоса", "xp": 30},
    {"key": "pitch_pre", "label": "Преза без MVP", "hint": "Problem/solution deck до продукта — сгенерирован и сохранён", "xp": 40},
    {"key": "pitch", "label": "Питч на проверку", "hint": "Питч проанализирован AI, score ≥ 60", "xp": 50},
    {"key": "finmodel", "label": "Финмодель", "hint": "Юнит-экономика B2B или B2C с цифрами", "xp": 60},
    {"key": "mvp", "label": "Создание MVP", "hint": "Есть рабочий продукт или лендинг с заявками", "xp": 50},
    {"key": "users", "label": "Первые пользователи", "hint": "Есть реальные пользователи вне команды", "xp": 80},
    {
        "key": "traction",
        "label": "Первая оплата",
        "hint": "Реальные деньги от клиента не из близкого круга — без бартера и «обещали»",
        "xp": 120,
    },
    {
        "key": "too",
        "label": "Открытие ТОО",
        "hint": "ТОО зарегистрировано; есть основание работать официально (договор, счёт)",
        "xp": 100,
    },
    {
        "key": "money",
        "label": "Повторяемый канал",
        "hint": "≥10 оплат из одного канала без ручной подстройки под каждого клиента",
        "xp": 200,
    },
]

MIN_STEPS = 8
MAX_STEPS = 12

VERTICAL_PRESETS = {
    "b2b_saas": "B2B SaaS: MVP → pilot клиенты → ARR → ТОО → инвестиции",
    "marketplace": "Marketplace: supply/demand → GMV → unit economics → ТОО → scale",
    "edtech": "Edtech: контент → первые ученики → retention → ТОО → B2B школы",
    "ai": "AI product: prototype → eval metrics → paying users → ТОО → enterprise",
}


def preset_hint(vertical: str | None) -> str:
    return VERTICAL_PRESETS.get(vertical or "", "")


def parse_steps_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return [dict(step) for step in ROADMAP_STEPS]
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [dict(step) for step in ROADMAP_STEPS]
    steps = data if isinstance(data, list) else data.get("steps", [])
    return normalize_steps(steps)


def normalize_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(steps[:MAX_STEPS]):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()[:90]
        if not label:
            continue
        hint = str(item.get("hint", "")).strip()[:220] or "Есть измеримый результат по шагу"
        try:
            xp = int(item.get("xp", 50))
        except (TypeError, ValueError):
            xp = 50
        out.append(
            {
                "key": str(item.get("key", f"step_{i}"))[:40],
                "label": label,
                "hint": hint,
                "xp": min(250, max(25, xp)),
            }
        )
    if len(out) < MIN_STEPS:
        return [dict(step) for step in ROADMAP_STEPS]
    last = out[-1]["label"].lower()
    last_key = (out[-1].get("key") or "").lower()
    if last_key != "money" and "денег" not in last and "деньги" not in last and "канал" not in last:
        out.append(
            {
                "key": "money",
                "label": "Повторяемый канал",
                "hint": "≥10 оплат из одного канала без ручной подстройки под каждого клиента",
                "xp": 200,
            }
        )
    else:
        out[-1]["key"] = "money"
        if not out[-1].get("hint"):
            out[-1]["hint"] = "≥10 оплат из одного канала без ручной подстройки под каждого клиента"
    return out[:MAX_STEPS]


def steps_for_startup(startup) -> list[dict[str, Any]]:
    if not startup:
        return [dict(step) for step in ROADMAP_STEPS]
    return parse_steps_json(getattr(startup, "roadmap_steps_json", None))


def dump_steps(steps: list[dict[str, Any]]) -> str:
    return json.dumps(steps, ensure_ascii=False)


def step_count(steps: list[dict[str, Any]] | None = None) -> int:
    return len(steps or ROADMAP_STEPS)


def step_at(index: int, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = steps or ROADMAP_STEPS
    if index < 0:
        return items[0]
    if index >= len(items):
        return items[-1]
    return items[index]


def is_finished(index: int, steps: list[dict[str, Any]] | None = None) -> bool:
    return index >= step_count(steps)


def branch_state(step_index: int, steps: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    items = steps or ROADMAP_STEPS
    result = []
    for i, step in enumerate(items):
        if i < step_index:
            status = "done"
        elif i == step_index:
            status = "active"
        else:
            status = "pending"
        result.append({**step, "index": i, "status": status})
    return result


def vertical_y_positions(count: int) -> list[float]:
    if count <= 1:
        return [50.0]
    top, bottom = 5.0, 93.0
    gap = (bottom - top) / (count - 1)
    return [round(top + i * gap, 1) for i in range(count)]


def branch_map_state(
    step_index: int,
    steps: list[dict[str, Any]] | None = None,
    step_logs: dict[int, Any] | None = None,
    startup=None,
    *,
    goals_done: int = 0,
) -> list[dict[str, Any]]:
    items = steps or ROADMAP_STEPS
    ys = vertical_y_positions(len(items))
    logs = step_logs or {}
    prev_anchor = getattr(startup, "roadmap_started_at", None) if startup else None
    nodes = []
    for i, step in enumerate(branch_state(step_index, items)):
        node = {**step, "y": ys[i]}
        if i == len(items) - 1:
            node["is_goal"] = True
        log = logs.get(i)
        if log and getattr(log, "completed_at", None):
            completed = log.completed_at
            node["completed_at"] = completed.strftime("%d.%m.%Y")
            node["completed_at_iso"] = completed.isoformat()
            if prev_anchor:
                node["days_taken"] = _days_between(prev_anchor, completed)
            prev_anchor = completed
        elif node.get("status") == "active" and startup:
            days = days_on_current_step(startup, items, logs)
            if days is not None:
                node["days_on_step"] = days
        nodes.append(node)
    if startup:
        from .step_branches import attach_micro_branches_to_map

        attach_micro_branches_to_map(nodes, startup, step_index, goals_done=goals_done)
    return nodes


def _days_between(start, end) -> int:
    from datetime import timezone

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max((end - start).days, 0)


def step_timeline(startup, steps: list[dict[str, Any]] | None = None, step_logs: dict[int, Any] | None = None) -> list[dict[str, Any]]:
    """Per-step status, completion date and duration for investor/admin views."""
    items = steps or steps_for_startup(startup)
    logs = step_logs if step_logs is not None else step_logs_by_index(startup)
    prev_anchor = getattr(startup, "roadmap_started_at", None) if startup else None
    timeline = []
    for i, step in enumerate(items):
        log = logs.get(i)
        entry = {
            "index": i,
            "label": step["label"],
            "hint": step.get("hint", ""),
            "status": "pending",
            "completed_at": None,
            "days": None,
            "evidence_url": None,
            "evidence_text": None,
        }
        if log and getattr(log, "completed_at", None):
            entry["status"] = "done"
            entry["completed_at"] = log.completed_at
            entry["days"] = _days_between(prev_anchor, log.completed_at) if prev_anchor else 0
            entry["evidence_url"] = getattr(log, "evidence_url", None)
            entry["evidence_text"] = getattr(log, "evidence_text", None)
            prev_anchor = log.completed_at
        elif i == startup.roadmap_step and not progress_stats(startup.roadmap_step, items)["finished"]:
            entry["status"] = "active"
            entry["days"] = days_on_current_step(startup, items, logs)
        timeline.append(entry)
    return timeline


def step_logs_by_index(startup) -> dict[int, Any]:
    if not startup:
        return {}
    return {log.step_index: log for log in getattr(startup, "step_logs", []) or []}


def too_step_index(steps: list[dict[str, Any]] | None = None) -> int | None:
    items = steps or ROADMAP_STEPS
    for i, step in enumerate(items):
        key = (step.get("key") or "").lower()
        label = (step.get("label") or "").lower()
        if key in {"too", "toо"} or "тоо" in label or " too" in f" {label}":
            return i
    return None


def too_status(startup, steps: list[dict[str, Any]] | None = None, step_logs: dict[int, Any] | None = None) -> dict[str, str]:
    if startup and getattr(startup, "too_registered_at", None):
        label = "Есть"
        if getattr(startup, "bin", None):
            label = f"Есть · BIN {startup.bin}"
        return {"state": "yes", "label": label}

    items = steps or (steps_for_startup(startup) if startup else ROADMAP_STEPS)
    logs = step_logs if step_logs is not None else step_logs_by_index(startup)
    idx = too_step_index(items)
    if idx is None:
        return {"state": "unknown", "label": "—"}
    if idx in logs or (startup and startup.roadmap_step > idx):
        return {"state": "yes", "label": "Есть"}
    return {"state": "no", "label": "Нет"}


def pace_between_steps(step_logs: list[Any]) -> dict[str, Any] | None:
    if len(step_logs) < 2:
        return None
    ordered = sorted(step_logs, key=lambda item: item.completed_at)
    gaps = []
    prev = ordered[0].completed_at
    for log in ordered[1:]:
        delta = (log.completed_at - prev).days
        gaps.append(max(delta, 0))
        prev = log.completed_at
    span = (ordered[-1].completed_at - ordered[0].completed_at).days
    return {"avg_days": round(sum(gaps) / len(gaps), 1), "total_days": max(span, 0)}


def days_on_current_step(startup, steps: list[dict[str, Any]] | None = None, step_logs: dict[int, Any] | None = None) -> int | None:
    if not startup or is_finished(startup.roadmap_step, steps):
        return None
    logs = step_logs if step_logs is not None else step_logs_by_index(startup)
    anchor = None
    if startup.roadmap_step > 0 and startup.roadmap_step - 1 in logs:
        anchor = logs[startup.roadmap_step - 1].completed_at
    elif startup.roadmap_started_at:
        anchor = startup.roadmap_started_at
    if not anchor:
        return None
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return max((now - anchor).days, 0)


def progress_stats(step_index: int, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = steps or ROADMAP_STEPS
    total = len(items)
    done = min(step_index, total)
    percent = int((done / total) * 100) if total else 0
    if is_finished(step_index, items):
        percent = 100
    return {"done": done, "total": total, "percent": percent, "finished": is_finished(step_index, items)}


def map_height_px(step_count: int) -> int:
    return max(380, min(720, 48 * step_count + 64))


def needs_roadmap_rebuild(startup) -> bool:
    if not startup:
        return False
    raw = getattr(startup, "roadmap_steps_json", None)
    if not raw:
        return True
    steps = parse_steps_json(raw)
    if len(steps) < MIN_STEPS:
        return True
    default_labels = [s["label"] for s in ROADMAP_STEPS]
    if [s["label"] for s in steps] == default_labels:
        return True
    return False


def advance_roadmap(
    user,
    startup,
    *,
    report: str | None = None,
    evidence_url: str | None = None,
    validation_request_id: int | None = None,
) -> str | None:
    from datetime import datetime, timezone

    from ..access import is_investor
    from ..models import db
    from ..models.entities import Activity, RoadmapStepLog

    steps = steps_for_startup(startup)
    if is_finished(startup.roadmap_step, steps):
        return None

    step = step_at(startup.roadmap_step, steps)
    completed_index = startup.roadmap_step
    startup.roadmap_step += 1
    startup.stage = step_at(startup.roadmap_step, steps)["label"]
    startup.traction = min(100, startup.traction + 18)
    startup.health = min(100, startup.health + 14)
    if not is_investor(user):
        user.score = (user.score or 0) + step["xp"]
        user.streak = (user.streak or 0) + 1

    report_text = (report or "").strip()

    if not RoadmapStepLog.query.filter_by(startup_id=startup.id, step_index=completed_index).first():
        log = RoadmapStepLog(
            startup_id=startup.id,
            step_index=completed_index,
            step_key=step.get("key", ""),
            step_label=step["label"],
            completed_at=datetime.now(timezone.utc),
            evidence_url=evidence_url,
            evidence_text=report_text[:500] if report_text else None,
            validation_request_id=validation_request_id,
        )
        db.session.add(log)
    elif evidence_url:
        existing_log = RoadmapStepLog.query.filter_by(
            startup_id=startup.id, step_index=completed_index
        ).first()
        if existing_log:
            existing_log.evidence_url = evidence_url

    if step.get("key") == "too" or "тоо" in step.get("label", "").lower():
        startup.too_registered_at = datetime.now(timezone.utc)

    db.session.add_all([startup, user])

    ship_body = report_text[:500] if report_text else f"Проект «{startup.name}» перешёл на следующий этап пути к деньгам."
    db.session.add(
        Activity(
            kind="ship",
            title=f"Шаг завершён: {step['label']}",
            body=ship_body,
            impact=step["xp"],
            user_id=user.id,
            startup_id=startup.id,
        )
    )
    if report_text:
        db.session.add(
            Activity(
                kind="post",
                title=f"Отчёт: {step['label']}",
                body=report_text[:500],
                impact=0,
                user_id=user.id,
                startup_id=startup.id,
            )
        )

    db.session.commit()

    if is_finished(startup.roadmap_step, steps):
        return "Финальный шаг «Повторяемый канал» закрыт. Ветка пройдена."
    next_step = step_at(startup.roadmap_step, steps)
    return f"Шаг «{step['label']}» закрыт. Активен: «{next_step['label']}»."
