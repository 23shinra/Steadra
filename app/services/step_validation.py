from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..models import db
from ..models.entities import StepValidationRequest, User
from .ai_agent import validate_step_report
from .notifications import notify
from .roadmap import advance_roadmap, is_finished, step_at, step_logs_by_index, steps_for_startup


def save_validation_evidence(startup_id: int, upload: FileStorage | None) -> tuple[str, str] | None:
    if not upload or not upload.filename:
        return None
    folder = Path(current_app.config.get("DOCUMENTS_FOLDER", "uploads/documents")) / "validations"
    folder.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(upload.filename)
    path = folder / f"{startup_id}_{int(datetime.now(timezone.utc).timestamp())}_{filename}"
    upload.save(path)
    return filename, str(path)


def pending_for_startup(startup_id: int, step_index: int | None = None) -> StepValidationRequest | None:
    q = StepValidationRequest.query.filter_by(startup_id=startup_id).filter(
        StepValidationRequest.status.in_(
            [
                StepValidationRequest.STATUS_PENDING_AI,
                StepValidationRequest.STATUS_PENDING_ADMIN,
            ]
        )
    )
    if step_index is not None:
        q = q.filter_by(step_index=step_index)
    return q.order_by(StepValidationRequest.created_at.desc()).first()


def submit_step_validation(
    user: User,
    startup,
    *,
    report: str,
    evidence_url: str | None = None,
    evidence_file: FileStorage | None = None,
) -> tuple[StepValidationRequest | None, str]:
    steps = steps_for_startup(startup)
    if is_finished(startup.roadmap_step, steps):
        return None, "Ветка уже пройдена."

    existing = pending_for_startup(startup.id, startup.roadmap_step)
    if existing:
        if existing.status == StepValidationRequest.STATUS_PENDING_ADMIN:
            return existing, "Отчёт уже прошёл AI-проверку и ждёт подтверждения админа."
        return existing, "Заявка на проверку уже отправлена."

    step = step_at(startup.roadmap_step, steps)
    evidence_meta = save_validation_evidence(startup.id, evidence_file)
    req = StepValidationRequest(
        startup_id=startup.id,
        user_id=user.id,
        step_index=startup.roadmap_step,
        step_key=step.get("key", ""),
        step_label=step["label"],
        report=report.strip()[:500],
        evidence_url=(evidence_url or "").strip()[:500] or None,
        status=StepValidationRequest.STATUS_PENDING_AI,
    )
    if evidence_meta:
        req.evidence_filename, req.evidence_filepath = evidence_meta
    db.session.add(req)
    db.session.commit()

    return run_ai_validation(req, user, startup, steps)


def run_ai_validation(
    req: StepValidationRequest,
    user: User,
    startup,
    steps: list | None = None,
) -> tuple[StepValidationRequest, str]:
    steps = steps or steps_for_startup(startup)
    logs = step_logs_by_index(startup)
    step = step_at(req.step_index, steps)

    prev_log = logs.get(req.step_index - 1) if req.step_index > 0 else None
    if prev_log:
        prev_summary = (
            f"Шаг «{prev_log.step_label}» закрыт {prev_log.completed_at.strftime('%d.%m.%Y')}. "
            f"Отчёт: {prev_log.evidence_text or '—'}. Proof: {prev_log.evidence_url or '—'}"
        )
    elif req.step_index == 0:
        from ..models.entities import AiThread

        thread = (
            AiThread.query.filter_by(startup_id=startup.id, user_id=user.id)
            .order_by(AiThread.id.desc())
            .first()
        )
        if thread:
            prev_summary = (
                f"Старт из AI-roast: «{thread.idea_name}», score={thread.roast_score or '—'}"
            )
        else:
            prev_summary = "Первый шаг — предыдущий этап: прожарка идеи в AI-чате."
    else:
        prev_summary = "Предыдущий шаг не закрыт — отклоняй заявку."

    try:
        result = validate_step_report(
            user,
            startup,
            step,
            req.step_index,
            len(steps),
            report=req.report,
            evidence_url=req.evidence_url,
            previous_step_summary=prev_summary,
        )
    except Exception:
        req.status = StepValidationRequest.STATUS_AI_REJECTED
        req.ai_feedback = "AI-проверка временно недоступна. Попробуй позже."
        db.session.commit()
        return req, req.ai_feedback

    req.ai_verdict = (result.get("admin_summary") or "")[:500]
    req.ai_feedback = (result.get("feedback") or "")[:900]
    req.ai_confidence = int(result.get("confidence") or 0)
    req.ai_approved_at = datetime.now(timezone.utc)

    approved = bool(result.get("approved")) and bool(result.get("previous_step_ok"))
    if approved and req.ai_confidence >= 70:
        req.status = StepValidationRequest.STATUS_PENDING_ADMIN
        db.session.commit()
        notify(
            user,
            "step_validation",
            "AI одобрил отчёт",
            f"Шаг «{req.step_label}» прошёл AI-проверку. Ждём подтверждения админа.",
            url_for("main.progress_page", startup=startup.id),
        )
        return req, (
            f"AI подтвердил выполнение шага «{req.step_label}». "
            "Админ проверит отчёт лично — после этого шаг закроется на карте."
        )

    req.status = StepValidationRequest.STATUS_AI_REJECTED
    missing = result.get("missing_criteria") or []
    if missing:
        req.ai_feedback += " Не хватает: " + "; ".join(str(m) for m in missing[:4])
    db.session.commit()
    return req, req.ai_feedback or "AI не подтвердил выполнение шага. Дополни отчёт."


def admin_approve(req: StepValidationRequest, admin_id: int | None = None, notes: str | None = None) -> str:
    if req.status != StepValidationRequest.STATUS_PENDING_ADMIN:
        return "Заявка не ждёт решения админа."

    startup = req.startup
    user = req.user
    req.status = StepValidationRequest.STATUS_ADMIN_APPROVED
    req.admin_id = admin_id
    req.admin_notes = (notes or "").strip()[:500] or None
    req.admin_decided_at = datetime.now(timezone.utc)
    db.session.add(req)
    db.session.commit()

    message = advance_roadmap(
        user,
        startup,
        report=req.report,
        evidence_url=req.evidence_url,
        validation_request_id=req.id,
    )
    from .achievements import check_and_grant

    check_and_grant(user, event="step_complete", startup=startup)
    notify(
        user,
        "step_approved",
        f"Шаг «{req.step_label}» подтверждён",
        "Админ одобрил отчёт. Карта обновлена.",
        url_for("main.progress_page", startup=startup.id),
    )
    return message or "Шаг подтверждён админом."


def admin_reject(req: StepValidationRequest, admin_id: int | None = None, notes: str | None = None) -> str:
    if req.status != StepValidationRequest.STATUS_PENDING_ADMIN:
        return "Заявка не ждёт решения админа."

    req.status = StepValidationRequest.STATUS_ADMIN_REJECTED
    req.admin_id = admin_id
    req.admin_notes = (notes or "").strip()[:500] or None
    req.admin_decided_at = datetime.now(timezone.utc)
    db.session.commit()

    reason = req.admin_notes or "Нужен более подробный отчёт с доказательствами."
    notify(
        req.user,
        "step_rejected",
        f"Шаг «{req.step_label}»: нужна доработка",
        reason,
        url_for("main.progress_page", startup=req.startup_id),
    )
    return "Отклонено. Фаундер получит уведомление."


def pending_admin_queue(limit: int = 50) -> list[StepValidationRequest]:
    return (
        StepValidationRequest.query.filter_by(status=StepValidationRequest.STATUS_PENDING_ADMIN)
        .order_by(StepValidationRequest.created_at.asc())
        .limit(limit)
        .all()
    )
