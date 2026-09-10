from datetime import datetime, timedelta, timezone

from flask import url_for

from ..access import is_investor
from ..models import db
from ..models.entities import Notification
from .roadmap import days_on_current_step, is_finished, progress_stats, step_at, steps_for_startup
from .team import primary_startup


def notify(user, kind: str, title: str, body: str, href: str) -> Notification:
    item = Notification(
        user_id=user.id,
        kind=kind,
        title=title[:160],
        body=body[:900],
        href=href[:255],
    )
    db.session.add(item)
    db.session.commit()

    if kind in {"step_stuck", "weekly_digest", "team_invite"}:
        from .push import send_push

        send_push(user, title, body, href)

    return item


NOTIFICATION_KIND_LABELS = {
    "weekly_digest": "Неделя на шаге",
    "step_stuck": "Застрял на шаге",
    "team_invite": "Приглашение в команду",
    "step_validation": "Отчёт на проверке",
    "step_approved": "Шаг одобрен",
    "step_rejected": "Шаг отклонён",
    "retention": "Напоминание",
    "goal": "Цели недели",
    "too_approved": "ТОО подтверждено",
    "too_rejected": "ТОО отклонено",
}


def notification_kind_label(kind: str | None) -> str:
    key = (kind or "").strip()
    return NOTIFICATION_KIND_LABELS.get(key, key.replace("_", " ").capitalize() if key else "—")


def unread_count(user) -> int:
    if not user:
        return 0
    return Notification.query.filter_by(user_id=user.id, read_at=None).count()


def list_for(user, limit: int = 40) -> list[Notification]:
    if not user:
        return []
    return (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


def mark_read(notification_id: int, user_id: int) -> bool:
    item = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not item or item.read_at:
        return False
    item.read_at = datetime.now(timezone.utc)
    db.session.add(item)
    db.session.commit()
    return True


def mark_all_read(user) -> None:
    if not user:
        return
    now = datetime.now(timezone.utc)
    Notification.query.filter_by(user_id=user.id, read_at=None).update({"read_at": now})
    db.session.commit()


def notify_team_invite(invitee, inviter, startup, invite_id: int) -> Notification:
    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    current = step_at(startup.roadmap_step, steps) if not is_finished(startup.roadmap_step, steps) else None
    step_line = current["label"] if current else "Ветка пройдена"
    body = (
        f"{inviter.name} зовёт в команду «{startup.name}». "
        f"Прогресс {progress['done']}/{progress['total']} ({progress['percent']}%). "
        f"Сейчас: {step_line}."
    )
    return notify(
        invitee,
        "team_invite",
        f"Приглашение в «{startup.name}»",
        body,
        url_for("main.team_invite_detail", invite_id=invite_id),
    )


def _recent_kind(user_id: int, kind: str, days: int) -> Notification | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        Notification.query.filter(
            Notification.user_id == user_id,
            Notification.kind == kind,
            Notification.created_at >= cutoff,
        )
        .order_by(Notification.created_at.desc())
        .first()
    )


def _maybe_notify_stuck(user, startup, days: int, steps) -> None:
    if _recent_kind(user.id, "step_stuck", 7):
        return
    step = step_at(startup.roadmap_step, steps)
    notify(
        user,
        "step_stuck",
        f"Застрял на шаге «{step['label']}»?",
        f"Уже {days} дней на этом этапе. Открой карту или спроси AI — что сделать сегодня.",
        url_for("main.progress_page", startup=startup.id),
    )


def _maybe_weekly_digest(user, startup, steps) -> None:
    if _recent_kind(user.id, "weekly_digest", 7):
        return
    progress = progress_stats(startup.roadmap_step, steps)
    if progress["finished"]:
        return
    step = step_at(startup.roadmap_step, steps)
    from .step_goals import weekly_goals_summary

    weekly = weekly_goals_summary(startup)
    tasks_left = weekly["total"] - weekly["done"] if weekly else 0
    notify(
        user,
        "weekly_digest",
        f"Неделя на шаге «{step['label']}»",
        f"Путь: {progress['percent']}%. Задач на неделю осталось: {tasks_left}.",
        url_for("main.progress_page", startup=startup.id),
    )


def run_retention_checks(user) -> None:
    if not user or is_investor(user):
        return
    startup = primary_startup(user)
    if not startup:
        return
    steps = steps_for_startup(startup)
    if is_finished(startup.roadmap_step, steps):
        return

    days = days_on_current_step(startup, steps)
    if days is not None and days >= 7:
        _maybe_notify_stuck(user, startup, days, steps)
    _maybe_weekly_digest(user, startup, steps)
