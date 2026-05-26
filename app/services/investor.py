from ..models import db
from ..models.entities import InvestorFavorite, Startup, TeamMember, User
from .roadmap import (
    days_on_current_step,
    pace_between_steps,
    progress_stats,
    step_logs_by_index,
    step_timeline,
    steps_for_startup,
    too_status,
)

TEAM_ROLE_LABELS = {
    "owner": "Основатель",
    "ceo": "CEO",
    "cto": "CTO",
    "marketing": "Marketing",
    "member": "Участник",
}


def team_detail(startup: Startup) -> dict:
    rows = [{"user": startup.owner, "role": "owner", "role_label": TEAM_ROLE_LABELS["owner"], "is_owner": True}]
    for tm in TeamMember.query.filter_by(startup_id=startup.id).order_by(TeamMember.joined_at.asc()).all():
        user = db.session.get(User, tm.user_id)
        if not user or user.id == startup.owner_id:
            continue
        role = (tm.team_role or "member").lower()
        rows.append(
            {
                "user": user,
                "role": role,
                "role_label": TEAM_ROLE_LABELS.get(role, tm.team_role or "Участник"),
                "is_owner": False,
            }
        )
    return {"count": len(rows), "members": rows}


def investor_startup_bundle(startup: Startup) -> dict:
    steps = steps_for_startup(startup)
    logs = step_logs_by_index(startup)
    stats = progress_stats(startup.roadmap_step, steps)
    pace = pace_between_steps(list(logs.values()))
    timeline = step_timeline(startup, steps, logs)
    total_completed_days = sum(t["days"] or 0 for t in timeline if t["status"] == "done")
    return {
        "startup": startup,
        "owner": startup.owner,
        "steps_count": len(steps),
        "progress": stats,
        "too": too_status(startup, steps, logs),
        "pace": pace,
        "current_step_days": days_on_current_step(startup, steps, logs),
        "team": team_detail(startup),
        "step_timeline": timeline,
        "total_completed_days": total_completed_days,
        "logs": logs,
    }


def favorite_startup_ids(investor: User | None) -> set[int]:
    if not investor:
        return set()
    rows = InvestorFavorite.query.filter_by(investor_id=investor.id).all()
    return {row.startup_id for row in rows}


def is_favorited(investor: User | None, startup_id: int) -> bool:
    if not investor:
        return False
    return startup_id in favorite_startup_ids(investor)


def toggle_favorite(investor: User, startup_id: int) -> bool:
    existing = InvestorFavorite.query.filter_by(investor_id=investor.id, startup_id=startup_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return False
    db.session.add(InvestorFavorite(investor_id=investor.id, startup_id=startup_id))
    db.session.commit()
    return True


def _row_for_startup(startup: Startup, favorite_ids: set[int]) -> dict:
    bundle = investor_startup_bundle(startup)
    bundle["is_favorite"] = startup.id in favorite_ids
    return bundle


def candidate_rows(investor: User | None = None, *, only_favorites: bool = False) -> list[dict]:
    favorite_ids = favorite_startup_ids(investor)
    if only_favorites:
        if not favorite_ids:
            return []
        startups = Startup.query.filter(Startup.id.in_(favorite_ids)).order_by(Startup.id.desc()).all()
    else:
        startups = Startup.query.order_by(Startup.id.desc()).all()
    return [_row_for_startup(startup, favorite_ids) for startup in startups]
