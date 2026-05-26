import random

from ..models import db
from ..models.entities import Activity, ActivityComment, User

COMMENT_SNIPPETS = [
    "Огонь, так держать!",
    "Крутая динамика, респект.",
    "А как вы привлекаете первых пользователей?",
    "Подписался на ваш путь — интересно.",
    "Это уже похоже на traction.",
    "Есть место для партнёрства?",
    "Сильный шаг, видно движение.",
    "Делитесь цифрами через неделю?",
    "Мотивирует, сам на похожем этапе.",
    "Классный фокус, без воды.",
    "Какой канал сработал лучше всего?",
    "Верю в команду, продолжайте.",
    "Хочу так же закрыть свой чеклист.",
    "Полезно, спасибо что делитесь.",
    "Жду апдейт по следующему шагу.",
]


def ensure_activity_comments() -> None:
    users = User.query.all()
    activities = Activity.query.all()
    if len(users) < 2 or not activities:
        return

    changed = False
    for activity in activities:
        existing = ActivityComment.query.filter_by(activity_id=activity.id).count()
        if existing >= 2:
            continue
        others = [user for user in users if user.id != activity.user_id]
        if not others:
            continue
        rng = random.Random(activity.id * 17 + len(activity.body))
        target = rng.randint(2, 5)
        for _ in range(target):
            author = rng.choice(others)
            body = rng.choice(COMMENT_SNIPPETS)
            db.session.add(
                ActivityComment(
                    activity_id=activity.id,
                    user_id=author.id,
                    body=body,
                )
            )
            changed = True

    if changed:
        db.session.commit()
