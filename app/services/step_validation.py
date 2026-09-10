from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..models import db
from ..models.entities import StepValidationRequest, User
from .ai_agent import validate_step_report
from .notifications import notify
from .roadmap import advance_roadmap, is_finished, step_at, step_logs_by_index, steps_for_startup


def _progress_href(startup_id: int) -> str:
    """Safe progress link even outside an HTTP request (CLI/jobs)."""
    try:
        return url_for("main.progress_page", startup=startup_id)
    except RuntimeError:
        return f"/progress?startup={startup_id}"


ALLOWED_EVIDENCE_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx"}
POLL_PUBLISH_GRACE_HOURS = 24
POLL_STEP_KEYS = {"idea_poll", "idea_polling"}
PITCH_STEP_KEYS = {"pitch_pre", "pitch", "pre_mvp_pitch", "pitch_pre_mvp", "pitch_check", "pitch_validated"}
PITCH_PASS_SCORE = 60


def _is_poll_step_key(step_key: str | None) -> bool:
    from .step_prompts import STEP_KEY_ALIASES

    key = (step_key or "").lower().strip()
    return STEP_KEY_ALIASES.get(key, key) in POLL_STEP_KEYS or key in POLL_STEP_KEYS


def is_pitch_related_step(step: dict) -> bool:
    from .step_prompts import infer_step_key

    key = (step.get("key") or "").lower().strip()
    if key in PITCH_STEP_KEYS:
        return True
    return infer_step_key(step) in {"pitch_pre", "pitch"}


def idea_poll_meets_criteria(startup) -> tuple[bool, str]:
    from ..models.entities import IdeaPoll
    from .idea_poll import poll_for_startup

    poll = poll_for_startup(startup.id)
    if not poll:
        return False, "no_poll"
    total_votes = poll.yes_count + poll.no_count + poll.maybe_count
    if total_votes < 3:
        return False, "need_votes"
    if poll.verdict == IdeaPoll.VERDICT_WEAK:
        return False, "weak_verdict"
    if poll.verdict in (IdeaPoll.VERDICT_GOOD, IdeaPoll.VERDICT_UNCLEAR) and poll.score >= 40:
        return True, ""
    return False, "need_votes"


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def expire_poll_validations() -> int:
    """Reject idea_poll requests that missed the 24h publish deadline or stuck on weak poll."""
    from ..models.entities import IdeaPoll
    from .idea_poll import poll_for_startup

    count = 0
    now = datetime.now(timezone.utc)
    reqs = (
        StepValidationRequest.query.filter_by(status=StepValidationRequest.STATUS_PENDING_POLL)
        .all()
    )
    for req in reqs:
        if not _is_poll_step_key(req.step_key):
            continue
        poll = poll_for_startup(req.startup_id)
        if poll and poll.verdict == IdeaPoll.VERDICT_WEAK:
            req.status = StepValidationRequest.STATUS_AI_REJECTED
            req.ai_feedback = (
                "Опрос в ленте дал слабый вердикт. "
                "Переформулируй гипотезу и отправь отчёт заново."
            )
            notify(
                req.user,
                "step_rejected",
                f"Шаг «{req.step_label}»: слабый опрос",
                req.ai_feedback,
                _progress_href(req.startup_id),
            )
            count += 1
            continue
        if poll:
            continue
        deadline = _utc(req.poll_deadline_at)
        if not deadline or now <= deadline:
            continue
        req.status = StepValidationRequest.STATUS_AI_REJECTED
        req.ai_feedback = (
            "Срок публикации опроса истёк (24 часа с момента отправки отчёта). "
            "Отправь отчёт заново и опубликуй опрос в ленте."
        )
        notify(
            req.user,
            "step_rejected",
            f"Шаг «{req.step_label}»: срок истёк",
            req.ai_feedback,
            _progress_href(req.startup_id),
        )
        count += 1
    if count:
        db.session.commit()
    return count


def try_advance_poll_validation(startup_id: int) -> bool:
    """Move pending_poll → pending_admin once poll is live and has enough votes."""
    req = pending_for_startup(startup_id)
    if not req or req.status != StepValidationRequest.STATUS_PENDING_POLL:
        return False
    if not _is_poll_step_key(req.step_key):
        return False
    ok, _ = idea_poll_meets_criteria(req.startup)
    if not ok:
        return False
    req.status = StepValidationRequest.STATUS_PENDING_ADMIN
    req.poll_deadline_at = None
    db.session.commit()
    notify(
        req.user,
        "step_validation",
        "Опрос готов — ждём админа",
        f"Шаг «{req.step_label}»: опрос опубликован и набрал голоса. Админ проверит отчёт.",
        _progress_href(startup_id),
    )
    return True


def _release_stuck_poll_request(req: StepValidationRequest, startup) -> bool:
    """If pending_poll cannot progress, reject it so founder can resubmit."""
    from ..models.entities import IdeaPoll
    from .idea_poll import poll_for_startup

    if req.status != StepValidationRequest.STATUS_PENDING_POLL:
        return False
    if not _is_poll_step_key(req.step_key):
        return False

    poll = poll_for_startup(startup.id)
    now = datetime.now(timezone.utc)
    deadline = _utc(req.poll_deadline_at)
    stuck_reason = None

    if poll and poll.verdict == IdeaPoll.VERDICT_WEAK:
        stuck_reason = (
            "Опрос дал слабый вердикт. Переформулируй гипотезу и отправь отчёт заново."
        )
    elif poll:
        ok, reason = idea_poll_meets_criteria(startup)
        total = poll.yes_count + poll.no_count + poll.maybe_count
        if not ok and total >= 3 and reason != "need_votes":
            stuck_reason = (
                "Опрос набрал голоса, но не проходит критерий. "
                "Обнови гипотезу или дождись эскалации к админу."
            )
    elif deadline and now > deadline:
        stuck_reason = (
            "Срок публикации опроса истёк. Отправь отчёт заново и опубликуй опрос в ленте."
        )

    if not stuck_reason:
        return False

    req.status = StepValidationRequest.STATUS_AI_REJECTED
    req.ai_feedback = stuck_reason
    db.session.commit()
    return True


def poll_pending_message_for(req: StepValidationRequest, startup) -> str:
    return _pending_poll_message(req, startup)


def _pending_poll_message(req: StepValidationRequest, startup) -> str:
    from .idea_poll import poll_for_startup

    poll = poll_for_startup(startup.id)
    if poll:
        total = poll.yes_count + poll.no_count + poll.maybe_count
        return (
            f"AI принял отчёт по шагу «{req.step_label}». "
            f"Опрос уже в ленте — собери минимум 3 голоса (сейчас {total}). "
            "После этого заявка автоматически уйдёт админу."
        )
    deadline = _utc(req.poll_deadline_at)
    if deadline:
        local = deadline.astimezone(timezone(timedelta(hours=5)))
        until = local.strftime("%d.%m %H:%M")
        return (
            f"AI принял отчёт по шагу «{req.step_label}». "
            f"Опубликуй опрос в ленте до {until} (24 часа с момента отправки). "
            "После публикации собери минимум 3 голоса — тогда заявка уйдёт админу."
        )
    return (
        f"AI принял отчёт по шагу «{req.step_label}». "
        "Опубликуй опрос в ленте и собери минимум 3 голоса."
    )


def evidence_root() -> Path:
    folder = Path(current_app.config.get("DOCUMENTS_FOLDER", "uploads/documents"))
    if not folder.is_absolute():
        folder = Path(current_app.root_path).parent / folder
    return folder / "validations"


def save_validation_evidence(startup_id: int, upload: FileStorage | None) -> tuple[str, str] | None:
    if not upload or not upload.filename:
        return None
    filename = secure_filename(upload.filename)
    ext = Path(filename).suffix.lower()
    if not filename or ext not in ALLOWED_EVIDENCE_EXT:
        return None
    folder = evidence_root()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{startup_id}_{int(datetime.now(timezone.utc).timestamp())}_{filename}"
    upload.save(path)
    return filename, str(path)


def pending_for_startup(startup_id: int, step_index: int | None = None) -> StepValidationRequest | None:
    q = StepValidationRequest.query.filter_by(startup_id=startup_id).filter(
        StepValidationRequest.status.in_(
            [
                StepValidationRequest.STATUS_PENDING_AI,
                StepValidationRequest.STATUS_PENDING_POLL,
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
        if existing.status == StepValidationRequest.STATUS_PENDING_POLL:
            if _release_stuck_poll_request(existing, startup):
                existing = None
            else:
                return existing, _pending_poll_message(existing, startup)
        if existing:
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
        if _is_poll_step_key(req.step_key):
            poll_ok, _ = idea_poll_meets_criteria(startup)
            if not poll_ok:
                req.status = StepValidationRequest.STATUS_PENDING_POLL
                from .idea_poll import poll_for_startup

                if not poll_for_startup(startup.id):
                    req.poll_deadline_at = datetime.now(timezone.utc) + timedelta(hours=POLL_PUBLISH_GRACE_HOURS)
                else:
                    req.poll_deadline_at = None
                db.session.commit()
                message = _pending_poll_message(req, startup)
                notify(
                    user,
                    "step_validation",
                    "Отчёт принят — опубликуй опрос",
                    message,
                    _progress_href(startup.id),
                )
                return req, message

        req.status = StepValidationRequest.STATUS_PENDING_ADMIN
        db.session.commit()
        notify(
            user,
            "step_validation",
            "AI одобрил отчёт",
            f"Шаг «{req.step_label}» прошёл AI-проверку. Ждём подтверждения админа.",
            _progress_href(startup.id),
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
    if req.status not in (
        StepValidationRequest.STATUS_PENDING_ADMIN,
        StepValidationRequest.STATUS_PENDING_POLL,
    ):
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
        _progress_href(startup.id),
    )
    return message or "Шаг подтверждён админом."


def admin_reject(req: StepValidationRequest, admin_id: int | None = None, notes: str | None = None) -> str:
    if req.status not in (
        StepValidationRequest.STATUS_PENDING_ADMIN,
        StepValidationRequest.STATUS_PENDING_POLL,
    ):
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
        _progress_href(req.startup_id),
    )
    return "Отклонено. Фаундер получит уведомление."


def pending_admin_queue(limit: int = 50) -> list[StepValidationRequest]:
    return (
        StepValidationRequest.query.filter(
            StepValidationRequest.status.in_(
                [
                    StepValidationRequest.STATUS_PENDING_ADMIN,
                    StepValidationRequest.STATUS_PENDING_POLL,
                ]
            )
        )
        .order_by(StepValidationRequest.created_at.asc())
        .limit(limit)
        .all()
    )


def maybe_complete_pitch_step(user: User, startup, analysis: dict) -> str | None:
    """Close pitch-related roadmap step when AI deck score is ≥ 60."""
    try:
        score = int(analysis.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    if score < PITCH_PASS_SCORE:
        return None

    steps = steps_for_startup(startup)
    if is_finished(startup.roadmap_step, steps):
        return None

    step = step_at(startup.roadmap_step, steps)
    if not is_pitch_related_step(step):
        return None

    if pending_for_startup(startup.id, startup.roadmap_step):
        return None

    logs = step_logs_by_index(startup)
    if startup.roadmap_step in logs:
        return None

    summary = (analysis.get("summary") or "").strip()
    report = f"AI-разбор презентации: score {score}/100."
    if summary:
        report = f"{report} {summary}"[:500]

    doc_id = analysis.get("doc_id") or (analysis.get("attach") or {}).get("doc_id")
    evidence_url = None
    if doc_id:
        try:
            evidence_url = url_for(
                "extensions.download_document",
                startup_id=startup.id,
                doc_id=int(doc_id),
            )
        except RuntimeError:
            evidence_url = f"/startup/{startup.id}/documents/{doc_id}"

    now = datetime.now(timezone.utc)
    req = StepValidationRequest(
        startup_id=startup.id,
        user_id=user.id,
        step_index=startup.roadmap_step,
        step_key=step.get("key", ""),
        step_label=step["label"],
        report=report,
        evidence_url=evidence_url,
        status=StepValidationRequest.STATUS_ADMIN_APPROVED,
        ai_verdict=f"Автозакрытие: AI pitch score {score} ≥ {PITCH_PASS_SCORE}",
        ai_feedback=f"Презентация набрала {score}/100 — шаг закрыт автоматически.",
        ai_confidence=min(99, max(70, score)),
        ai_approved_at=now,
        admin_notes=f"Авто: AI pitch score {score} ≥ {PITCH_PASS_SCORE}",
        admin_decided_at=now,
    )
    db.session.add(req)
    db.session.flush()

    message = advance_roadmap(
        user,
        startup,
        report=report,
        evidence_url=evidence_url,
        validation_request_id=req.id,
    )
    from .achievements import check_and_grant

    check_and_grant(user, event="step_complete", startup=startup)
    notify(
        user,
        "step_approved",
        f"Шаг «{step['label']}» закрыт",
        f"AI-разбор питча: {score}/100. Карта обновлена.",
        _progress_href(startup.id),
    )
    db.session.commit()
    return message or f"Шаг «{step['label']}» закрыт — score {score}."
