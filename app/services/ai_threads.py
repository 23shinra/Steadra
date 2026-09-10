from __future__ import annotations

from datetime import datetime, timezone

from ..models import db
from ..models.entities import AiMessage, AiThread, Startup, User
import json

THREAD_PHASE_LABELS: dict[str, str] = {
    "roast": "Прожарка идеи",
    "roadmap": "Путь к деньгам",
}

MAX_IDEAS = 3
IDEA_LIMIT_MESSAGE = "Можно развивать максимум 3 идеи. Заверши или продолжай текущие."


def thread_phase_label(phase: str | None) -> str:
    if not phase:
        return "—"
    return THREAD_PHASE_LABELS.get(phase, phase)


def owned_startup_count(user: User) -> int:
    return Startup.query.filter_by(owner_id=user.id).count()


def open_roast_thread_count(user: User) -> int:
    """Roast threads without a linked startup — each occupies an idea slot."""
    return (
        AiThread.query.filter_by(user_id=user.id, phase="roast")
        .filter(AiThread.startup_id.is_(None))
        .filter(AiThread.messages.any())
        .count()
    )


def idea_slots_used(user: User) -> int:
    return owned_startup_count(user) + open_roast_thread_count(user)


def can_start_idea(user: User) -> bool:
    return idea_slots_used(user) < MAX_IDEAS


def can_launch_startup(user: User) -> bool:
    return owned_startup_count(user) < MAX_IDEAS


def threads_for_user(user: User) -> list[AiThread]:
    return (
        AiThread.query.filter_by(user_id=user.id)
        .filter(AiThread.messages.any())
        .order_by(AiThread.updated_at.desc(), AiThread.id.desc())
        .all()
    )


def resolve_thread(user: User, thread_id: int | None) -> AiThread | None:
    if not thread_id:
        return None
    return AiThread.query.filter_by(id=thread_id, user_id=user.id).first()


def update_thread_summary(thread: AiThread, title: str) -> None:
    thread.title = title
    thread.updated_at = datetime.now(timezone.utc)
    db.session.add(thread)
    db.session.commit()


def create_thread(user: User, title: str = "Новый чат") -> AiThread:
    if not can_start_idea(user):
        raise ValueError(IDEA_LIMIT_MESSAGE)
    now = datetime.now(timezone.utc)
    thread = AiThread(user_id=user.id, title=title, created_at=now, updated_at=now)
    db.session.add(thread)
    db.session.commit()
    return thread


def history_for_thread(thread: AiThread, limit: int = 40) -> list[dict]:
    messages = (
        AiMessage.query.filter_by(thread_id=thread.id)
        .order_by(AiMessage.created_at.asc(), AiMessage.id.asc())
        .limit(limit)
        .all()
    )
    return [{"role": message.role, "content": message.content} for message in messages]


def compact_roast_history(thread: AiThread) -> int:
    """Keep only score percentage in roast cards after the idea is accepted."""
    changed = 0
    messages = AiMessage.query.filter_by(thread_id=thread.id).all()
    for message in messages:
        meta = message.meta
        if not isinstance(meta, dict):
            continue
        roast = meta.get("roast")
        if not isinstance(roast, dict):
            continue
        score = roast.get("score")
        if score is None and not meta.get("clarify") and not meta.get("show_validate"):
            continue
        slim_roast = {"score": int(score or 0)}
        if roast.get("verdict"):
            slim_roast["verdict"] = str(roast.get("verdict"))[:120]
        new_meta = {"roast": slim_roast}
        message.meta_json = json.dumps(new_meta, ensure_ascii=False)
        db.session.add(message)
        changed += 1
    if changed:
        db.session.commit()
    return changed


def add_message(thread: AiThread, role: str, content: str, meta: dict | None = None) -> AiMessage:
    payload = None
    if meta:
        payload = json.dumps(meta, ensure_ascii=False)
        if len(payload) > 20000:
            slim = dict(meta)
            roast = slim.get("roast")
            if isinstance(roast, dict):
                roast = dict(roast)
                roast["criteria"] = []
                slim["roast"] = roast
            payload = json.dumps(slim, ensure_ascii=False)
            if len(payload) > 20000:
                payload = json.dumps({"show_validate": bool(slim.get("show_validate"))}, ensure_ascii=False)
    message = AiMessage(thread_id=thread.id, role=role, content=content, meta_json=payload)
    thread.updated_at = datetime.now(timezone.utc)
    db.session.add(message)
    db.session.add(thread)
    db.session.commit()
    return message


def pitch_chat_intro(startup, analysis: dict | None = None) -> str:
    """Short mentor line after a deck upload — about the startup, not the filename."""
    name = (getattr(startup, "name", None) or "стартапа").strip() or "стартапа"
    score = None
    if isinstance(analysis, dict) and analysis.get("score") is not None:
        try:
            score = int(analysis.get("score"))
        except (TypeError, ValueError):
            score = None
    if score is None:
        return (
            f"Вот разбор по «{name}» — взял суть из презы: "
            "оценка дека и что стоит поправить перед инвестором."
        )
    if score >= 66:
        tone = "дек уже довольно сильный"
    elif score >= 46:
        tone = "есть база, но дек ещё сырой"
    else:
        tone = "преза пока слабая"
    return (
        f"Вот разбор по «{name}» исходя из презы: {tone}. "
        "Ниже — оценка и главные дыры, которые лучше закрыть."
    )


def ensure_pitch_in_thread(thread: AiThread | None, startup: Startup | None) -> bool:
    """If startup has a saved pitch analysis but chat has no pitch card, backfill it."""
    if not thread or not startup or not startup.pitch_analysis_json:
        return False
    for message in AiMessage.query.filter_by(thread_id=thread.id).order_by(AiMessage.id.asc()).all():
        meta = message.meta or {}
        if isinstance(meta.get("pitch"), dict):
            return False
    try:
        analysis = json.loads(startup.pitch_analysis_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(analysis, dict):
        return False
    filename = (analysis.get("filename") or "презентация")[:120]
    score = int(analysis.get("score") or 0)
    attach = analysis.get("attach") if isinstance(analysis.get("attach"), dict) else None
    if not attach:
        ext = filename.rsplit(".", 1)[-1].upper() if "." in filename else ""
        attach = {
            "kind": "document",
            "filename": filename,
            "ext": ext,
        }
        doc_id = analysis.get("doc_id")
        if doc_id and startup:
            from flask import url_for

            attach["doc_id"] = doc_id
            attach["download_url"] = url_for(
                "extensions.download_document",
                startup_id=startup.id,
                doc_id=int(doc_id),
            )
    compact = {
        "score": score,
        "verdict": "сильный" if score >= 66 else "нормальный" if score >= 46 else "слабый",
        "investor_ready": score >= 60,
        "summary": (analysis.get("summary") or "")[:500],
        "weaknesses": list(analysis.get("weaknesses") or [])[:3],
        "filename": filename,
        "delta": analysis.get("delta"),
        "doc_id": attach.get("doc_id"),
        "attach": attach,
    }
    add_message(
        thread,
        "user",
        filename,
        meta={"attach": attach},
    )
    add_message(
        thread,
        "assistant",
        pitch_chat_intro(startup, compact),
        meta={"pitch": compact},
    )
    return True
