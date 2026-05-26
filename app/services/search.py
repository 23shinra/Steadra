from __future__ import annotations

from sqlalchemy import or_

from ..models.entities import Activity, Startup, User


def search_all(query: str, *, kind: str | None = None, stage: str | None = None, has_too: bool | None = None, limit: int = 30) -> dict:
    q = (query or "").strip()
    if len(q) < 2:
        return {"users": [], "startups": [], "activities": []}

    pattern = f"%{q}%"
    users = (
        User.query.filter(
            User.account_type != "investor",
            or_(User.name.ilike(pattern), User.role.ilike(pattern)),
        )
        .order_by(User.score.desc())
        .limit(limit)
        .all()
    )

    startup_q = Startup.query.filter(
        or_(Startup.name.ilike(pattern), Startup.tagline.ilike(pattern))
    )
    if stage:
        startup_q = startup_q.filter(Startup.stage.ilike(f"%{stage}%"))
    if has_too is True:
        startup_q = startup_q.filter(Startup.too_registered_at.isnot(None))
    elif has_too is False:
        startup_q = startup_q.filter(Startup.too_registered_at.is_(None))
    startups = startup_q.order_by(Startup.traction.desc()).limit(limit).all()

    activity_q = Activity.query.filter(
        or_(Activity.title.ilike(pattern), Activity.body.ilike(pattern))
    )
    if kind and kind != "all":
        activity_q = activity_q.filter_by(kind=kind)
    activities = activity_q.order_by(Activity.created_at.desc()).limit(limit).all()

    return {"users": users, "startups": startups, "activities": activities}
