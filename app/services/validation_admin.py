from __future__ import annotations

from ..models.entities import AiMessage, AiThread, StepValidationRequest, StartupDocument
from .roadmap import step_logs_by_index, steps_for_startup, too_status


def validation_chat_messages(req: StepValidationRequest, limit: int = 40) -> list[AiMessage]:
    thread = (
        AiThread.query.filter_by(startup_id=req.startup_id, user_id=req.user_id)
        .order_by(AiThread.id.desc())
        .first()
    )
    if not thread:
        thread = AiThread.query.filter_by(user_id=req.user_id).order_by(AiThread.id.desc()).first()
    if not thread:
        return []
    return (
        AiMessage.query.filter_by(thread_id=thread.id)
        .order_by(AiMessage.created_at.asc())
        .all()[-limit:]
    )


def validation_bundle(req: StepValidationRequest) -> dict:
    startup = req.startup
    steps = steps_for_startup(startup)
    logs = step_logs_by_index(startup)
    documents = (
        StartupDocument.query.filter_by(startup_id=startup.id)
        .order_by(StartupDocument.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "request": req,
        "startup": startup,
        "user": req.user,
        "too": too_status(startup, steps, logs),
        "chat_messages": validation_chat_messages(req),
        "documents": documents,
        "has_attachment": bool(req.evidence_filepath or req.evidence_url),
    }


def validation_queue_bundles(limit: int = 50) -> list[dict]:
    from .step_validation import pending_admin_queue

    return [validation_bundle(req) for req in pending_admin_queue(limit)]
