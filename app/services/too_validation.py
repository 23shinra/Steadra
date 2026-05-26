from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..models import db
from ..models.entities import Activity, TooValidationRequest, User
from .notifications import notify
from .roadmap import advance_roadmap, step_at, steps_for_startup, too_step_index
from .step_validation import save_validation_evidence


def _normalize_bin(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")[:12]


def pending_too_for_startup(startup_id: int) -> TooValidationRequest | None:
    return (
        TooValidationRequest.query.filter_by(startup_id=startup_id, status=TooValidationRequest.STATUS_PENDING)
        .order_by(TooValidationRequest.created_at.desc())
        .first()
    )


def can_submit_too(startup) -> bool:
    if not startup or getattr(startup, "too_registered_at", None):
        return False
    if pending_too_for_startup(startup.id):
        return False
    steps = steps_for_startup(startup)
    idx = too_step_index(steps)
    if idx is None:
        return False
    return startup.roadmap_step >= max(0, idx - 1)


def chat_excerpt_for(startup, user, limit: int = 8) -> str:
    from ..models.entities import AiThread

    thread = (
        AiThread.query.filter_by(startup_id=startup.id, user_id=user.id)
        .order_by(AiThread.id.desc())
        .first()
    )
    if not thread:
        return ""
    from ..models.entities import AiMessage

    rows = (
        AiMessage.query.filter_by(thread_id=thread.id)
        .order_by(AiMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    lines = []
    for row in reversed(rows):
        role = "Фаундер" if row.role == "user" else "AI"
        text = " ".join((row.content or "").split())
        if text:
            lines.append(f"{role}: {text[:280]}")
    return "\n".join(lines)


def submit_too_validation(
    user: User,
    startup,
    *,
    company_name: str,
    bin_number: str,
    message: str,
    evidence_url: str | None = None,
    evidence_file: FileStorage | None = None,
) -> tuple[TooValidationRequest | None, str]:
    if not can_submit_too(startup):
        return None, "Сейчас нельзя отправить заявку на ТОО."
    company_name = company_name.strip()[:160]
    bin_clean = _normalize_bin(bin_number)
    if len(company_name) < 2:
        return None, "Укажи название компании."
    if len(bin_clean) != 12:
        return None, "BIN должен содержать 12 цифр."
    message = message.strip()[:900]
    if len(message) < 10:
        return None, "Опиши, что уже сделано по ТОО (минимум 10 символов)."

    evidence_meta = save_validation_evidence(startup.id, evidence_file)
    req = TooValidationRequest(
        startup_id=startup.id,
        user_id=user.id,
        company_name=company_name,
        bin=bin_clean,
        message=message,
        chat_excerpt=chat_excerpt_for(startup, user),
        evidence_url=(evidence_url or "").strip()[:500] or None,
    )
    if evidence_meta:
        req.evidence_filename, req.evidence_filepath = evidence_meta
    db.session.add(req)
    db.session.add(
        Activity(
            kind="post",
            title=f"Заявка на подтверждение ТОО: {company_name}",
            body=f"BIN {bin_clean}. {message[:300]}",
            impact=0,
            user_id=user.id,
            startup_id=startup.id,
        )
    )
    db.session.commit()
    return req, "Заявка отправлена. Админ проверит ТОО и ответит в уведомлениях."


def pending_too_queue(limit: int = 100) -> list[TooValidationRequest]:
    return (
        TooValidationRequest.query.filter_by(status=TooValidationRequest.STATUS_PENDING)
        .order_by(TooValidationRequest.created_at.asc())
        .limit(limit)
        .all()
    )


def too_validation_bundle(req: TooValidationRequest) -> dict:
    from .roadmap import step_logs_by_index, too_status

    startup = req.startup
    steps = steps_for_startup(startup)
    logs = step_logs_by_index(startup)
    step = step_at(startup.roadmap_step, steps)
    return {
        "request": req,
        "startup": startup,
        "user": req.user,
        "too": too_status(startup, steps, logs),
        "current_step": step,
        "chat_messages": validation_chat_messages_for_too(req),
    }


def validation_chat_messages_for_too(req: TooValidationRequest, limit: int = 40):
    from ..models.entities import AiMessage, AiThread

    thread = (
        AiThread.query.filter_by(startup_id=req.startup_id, user_id=req.user_id)
        .order_by(AiThread.id.desc())
        .first()
    )
    if not thread:
        return []
    return (
        AiMessage.query.filter_by(thread_id=thread.id)
        .order_by(AiMessage.created_at.asc())
        .all()[-limit:]
    )


def admin_approve_too(req: TooValidationRequest, admin_id: int | None = None, notes: str | None = None) -> str:
    if req.status != TooValidationRequest.STATUS_PENDING:
        return "Заявка уже обработана."
    startup = req.startup
    user = req.user
    startup.bin = req.bin
    startup.too_registered_at = datetime.now(timezone.utc)
    req.status = TooValidationRequest.STATUS_APPROVED
    req.admin_id = admin_id
    req.admin_notes = (notes or "").strip()[:500] or None
    req.decided_at = datetime.now(timezone.utc)
    db.session.add(startup)
    db.session.add(req)
    db.session.commit()

    steps = steps_for_startup(startup)
    step = step_at(startup.roadmap_step, steps)
    step_key = (step.get("key") or "").lower()
    step_label = (step.get("label") or "").lower()
    if step_key == "too" or "тоо" in step_label:
        advance_roadmap(
            user,
            startup,
            report=f"ТОО подтверждено админом: {req.company_name}, BIN {req.bin}. {req.message[:200]}",
            evidence_url=req.evidence_url,
        )

    notify(
        user,
        "too_approved",
        f"ТОО подтверждено: {req.company_name}",
        "Админ проверил документы. Статус ТОО обновлён на платформе.",
        url_for("main.progress_page", startup=startup.id),
    )
    return f"ТОО «{req.company_name}» подтверждено."


def admin_reject_too(req: TooValidationRequest, admin_id: int | None = None, notes: str | None = None) -> str:
    if req.status != TooValidationRequest.STATUS_PENDING:
        return "Заявка уже обработана."
    req.status = TooValidationRequest.STATUS_REJECTED
    req.admin_id = admin_id
    req.admin_notes = (notes or "").strip()[:500] or None
    req.decided_at = datetime.now(timezone.utc)
    db.session.commit()
    reason = req.admin_notes or "Приложи выписку eGov или справку с BIN."
    notify(
        req.user,
        "too_rejected",
        "ТОО не подтверждено",
        reason,
        url_for("main.progress_page", startup=req.startup_id),
    )
    return "Заявка отклонена."
