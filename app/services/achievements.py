from __future__ import annotations

from ..models import db
from ..models.entities import Achievement, User, UserAchievement

DEFAULT_ACHIEVEMENTS = [
    {"key": "registration", "title": "Регистрация", "description": "Создал аккаунт в Kangaroo", "icon": "signup"},
    {"key": "first_ship", "title": "Первый ship", "description": "Завершил первый шаг roadmap", "icon": "ship"},
    {"key": "streak_7", "title": "7 дней подряд", "description": "Streak 7+ дней", "icon": "streak"},
    {"key": "too_open", "title": "ТОО открыто", "description": "Зарегистрировал компанию", "icon": "company"},
    {"key": "xp_100", "title": "100 XP", "description": "Набрал 100 очков роста", "icon": "xp"},
    {"key": "first_post", "title": "Первый пост", "description": "Опубликовал в ленте", "icon": "post"},
    {"key": "roast_done", "title": "Прожарка пройдена", "description": "Прошёл AI roast идеи", "icon": "roast"},
]


ACHIEVEMENT_ORDER = [
    "registration",
    "roast_done",
    "first_ship",
    "first_post",
    "xp_100",
    "streak_7",
    "too_open",
]


def ensure_achievements() -> None:
    for item in DEFAULT_ACHIEVEMENTS:
        existing = Achievement.query.filter_by(key=item["key"]).first()
        if not existing:
            db.session.add(Achievement(**item))
        else:
            changed = False
            if existing.icon != item["icon"]:
                existing.icon = item["icon"]
                changed = True
            if existing.title != item["title"]:
                existing.title = item["title"]
                changed = True
            if existing.description != item["description"]:
                existing.description = item["description"]
                changed = True
            if changed:
                db.session.add(existing)
    db.session.commit()
    grant_registration_to_all()


def grant_registration_to_all() -> None:
    ach = Achievement.query.filter_by(key="registration").first()
    if not ach:
        return
    earned_ids = {
        row.user_id
        for row in UserAchievement.query.filter_by(achievement_id=ach.id).all()
    }
    for user in User.query.all():
        if user.id not in earned_ids:
            db.session.add(UserAchievement(user_id=user.id, achievement_id=ach.id))
    db.session.commit()


def grant(user: User, key: str) -> UserAchievement | None:
    ach = Achievement.query.filter_by(key=key).first()
    if not ach:
        return None
    existing = UserAchievement.query.filter_by(user_id=user.id, achievement_id=ach.id).first()
    if existing:
        return existing
    ua = UserAchievement(user_id=user.id, achievement_id=ach.id)
    db.session.add(ua)
    db.session.commit()
    return ua


def check_and_grant(user: User, *, event: str, startup=None) -> list[UserAchievement]:
    earned = []
    if event == "step_complete" and startup and startup.roadmap_step == 1:
        ua = grant(user, "first_ship")
        if ua:
            earned.append(ua)
    if event == "post":
        ua = grant(user, "first_post")
        if ua:
            earned.append(ua)
    if event == "roast":
        ua = grant(user, "roast_done")
        if ua:
            earned.append(ua)
    if user.score >= 100:
        ua = grant(user, "xp_100")
        if ua:
            earned.append(ua)
    if user.streak >= 7:
        ua = grant(user, "streak_7")
        if ua:
            earned.append(ua)
    if startup and getattr(startup, "too_registered_at", None):
        ua = grant(user, "too_open")
        if ua:
            earned.append(ua)
    return earned


def _achievement_progress(user: User, key: str, earned: bool) -> dict:
    if earned:
        return {"current": 1, "target": 1, "percent": 100}
    if key == "xp_100":
        current = min(user.score or 0, 100)
        return {"current": current, "target": 100, "percent": current}
    if key == "streak_7":
        current = min(user.streak or 0, 7)
        return {"current": current, "target": 7, "percent": round(current / 7 * 100) if current else 0}
    return {"current": 0, "target": 1, "percent": 0}


def _achievement_sort_key(achievement: Achievement) -> tuple[int, int]:
    try:
        return (ACHIEVEMENT_ORDER.index(achievement.key), achievement.id)
    except ValueError:
        return (999, achievement.id)


def achievements_for(user: User) -> list[dict]:
    from .i18n import achievement_labels, get_request_locale

    locale = get_request_locale()
    earned_ids = {ua.achievement_id for ua in UserAchievement.query.filter_by(user_id=user.id).all()}
    all_ach = sorted(Achievement.query.all(), key=_achievement_sort_key)
    return [
        {
            "achievement": a,
            "title": achievement_labels(a.key, locale)[0],
            "description": achievement_labels(a.key, locale)[1],
            "earned": a.id in earned_ids,
            "progress": _achievement_progress(user, a.key, a.id in earned_ids),
        }
        for a in all_ach
    ]


def achievements_summary(user: User) -> dict:
    items = achievements_for(user)
    total = len(items)
    earned = sum(1 for item in items if item["earned"])
    return {
        "entries": items,
        "earned": earned,
        "total": total,
        "percent": round(earned / total * 100) if total else 0,
    }
