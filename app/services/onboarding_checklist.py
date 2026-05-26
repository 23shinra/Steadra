from ..access import is_investor
from ..models.entities import Activity, AiThread, Startup


def has_ai_validated_startup(user) -> bool:
    """Проект создан через «Запустить путь» после прожарки AI."""
    if not user:
        return False
    return (
        Startup.query.filter(
            Startup.owner_id == user.id,
            Startup.roadmap_started_at.isnot(None),
        ).first()
        is not None
    )


def onboarding_task_status(user) -> dict | None:
    if not user or is_investor(user) or not user.onboarding_done:
        return None

    has_thread = AiThread.query.filter_by(user_id=user.id).first() is not None
    has_startup = Startup.query.filter_by(owner_id=user.id).first() is not None
    has_post = Activity.query.filter_by(user_id=user.id, kind="post").first() is not None

    tasks = [
        {"key": "idea", "label": "Опиши идею в AI", "done": has_thread},
        {"key": "roadmap", "label": "Запусти путь на карте", "done": has_startup},
        {"key": "post", "label": "Напиши первый пост", "done": has_post},
    ]

    if all(item["done"] for item in tasks):
        return None

    done_count = sum(1 for item in tasks if item["done"])
    return {"tasks": tasks, "done_count": done_count, "total": len(tasks)}


def onboarding_checklist(user) -> dict | None:
    from flask import url_for

    data = onboarding_task_status(user)
    if not data:
        return None

    hrefs = {
        "idea": url_for("main.ai", onboarding=1),
        "roadmap": url_for("main.ai"),
        "post": url_for("main.feed", compose=1),
    }
    tasks = [{**task, "href": hrefs[task["key"]]} for task in data["tasks"]]
    return {**data, "tasks": tasks}
