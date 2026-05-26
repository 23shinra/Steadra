from flask import url_for

from ..access import is_investor
from ..models.entities import Startup
from .roadmap import days_on_current_step, is_finished, progress_stats, step_at, steps_for_startup
from .step_goals import weekly_goals_summary


def _primary_startup(user):
    if not user:
        return None
    return Startup.query.filter_by(owner_id=user.id).order_by(Startup.id.desc()).first()


def mission_for_user(user) -> dict | None:
    if not user or is_investor(user):
        return None

    startup = _primary_startup(user)
    if not startup:
        return {
            "startup": None,
            "current_step": None,
            "progress": None,
            "days_on_step": None,
            "finished": False,
            "weekly_goals": None,
            "cta_url": url_for("main.ai", onboarding=1),
            "cta_label": "Запустить идею в AI",
            "ai_url": url_for("main.ai", onboarding=1),
            "feed_url": url_for("main.feed"),
            "progress_url": url_for("main.progress_page"),
        }

    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    days = days_on_current_step(startup, steps)
    finished = progress["finished"]
    current = None if finished else step_at(startup.roadmap_step, steps)
    weekly = weekly_goals_summary(startup)

    return {
        "startup": startup,
        "current_step": current,
        "progress": progress,
        "days_on_step": days,
        "finished": finished,
        "weekly_goals": weekly,
        "cta_url": url_for("main.progress_page", startup=startup.id),
        "cta_label": "Продолжить" if not finished else "Карта пройдена",
        "ai_url": url_for("main.ai"),
        "feed_url": url_for("main.feed", compose=1),
        "progress_url": url_for("main.progress_page", startup=startup.id),
    }
