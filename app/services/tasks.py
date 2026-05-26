"""Background task helpers (run inline or via cron/RQ)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from flask import current_app

from ..models import db
from ..models.entities import User
from ..services.notifications import notify


def run_retention_push_campaign() -> int:
    """Notify founders stuck on a step for 3+ days."""
    from ..models.entities import Startup
    from ..services.roadmap import days_on_current_step, is_finished, steps_for_startup

    count = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    for user in User.query.filter_by(account_type="user", onboarding_done=True).all():
        startup = Startup.query.filter_by(owner_id=user.id).order_by(Startup.id.desc()).first()
        if not startup:
            continue
        steps = steps_for_startup(startup)
        if is_finished(startup.roadmap_step, steps):
            continue
        days = days_on_current_step(startup, steps)
        if days is None or days < 3:
            continue
        if user.created_at and user.created_at > cutoff:
            continue
        notify(
            user,
            "retention",
            "Не застрял на шаге?",
            f"«{startup.name}»: уже {days} дн. на текущем шаге. Загляни в карту.",
            "/progress",
        )
        from .push import send_push

        send_push(user, "Kangaroo", f"Шаг ждёт: {startup.name}")
        count += 1
    return count


def run_weekly_goal_reminders() -> int:
    from ..models.entities import StepWeeklyGoal, Startup
    from ..services.step_goals import weekly_goals_summary

    count = 0
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    for startup in Startup.query.all():
        summary = weekly_goals_summary(startup)
        if not summary or summary.get("done") == summary.get("total"):
            continue
        user = db.session.get(User, startup.owner_id)
        if not user:
            continue
        notify(
            user,
            "goal",
            "Weekly goals",
            f"Завтра дедлайн целей недели для «{startup.name}».",
            f"/progress?startup={startup.id}",
        )
        count += 1
    return count
