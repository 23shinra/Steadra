from __future__ import annotations

from ..models import db
from ..models.entities import Achievement, User, UserAchievement

DEFAULT_ACHIEVEMENTS = [
    {"key": "first_ship", "title": "Первый ship", "description": "Завершил первый шаг roadmap", "icon": "🚀"},
    {"key": "streak_7", "title": "7 дней подряд", "description": "Streak 7+ дней", "icon": "🔥"},
    {"key": "too_open", "title": "ТОО открыто", "description": "Зарегистрировал компанию", "icon": "🏢"},
    {"key": "xp_100", "title": "100 XP", "description": "Набрал 100 очков роста", "icon": "⭐"},
    {"key": "first_post", "title": "Первый пост", "description": "Опубликовал в ленте", "icon": "✎"},
    {"key": "roast_done", "title": "Прожарка пройдена", "description": "Прошёл AI roast идеи", "icon": "🤖"},
]


def ensure_achievements() -> None:
    for item in DEFAULT_ACHIEVEMENTS:
        if not Achievement.query.filter_by(key=item["key"]).first():
            db.session.add(Achievement(**item))
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


def achievements_for(user: User) -> list[dict]:
    earned_ids = {ua.achievement_id for ua in UserAchievement.query.filter_by(user_id=user.id).all()}
    all_ach = Achievement.query.order_by(Achievement.id.asc()).all()
    return [
        {"achievement": a, "earned": a.id in earned_ids}
        for a in all_ach
    ]
