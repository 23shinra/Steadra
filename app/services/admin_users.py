from sqlalchemy import func

from ..access import ACCOUNT_INVESTOR, is_investor
from ..models import db
from ..models.entities import (
    Activity,
    ActivityComment,
    ActivityLike,
    AiThread,
    Notification,
    PushSubscription,
    Startup,
    TeamInvitation,
    User,
)
from .onboarding_checklist import has_ai_validated_startup, onboarding_checklist, onboarding_task_status
from .roadmap import days_on_current_step, progress_stats, step_at, step_logs_by_index, steps_for_startup, too_status
from .step_goals import weekly_goals_summary
from .team import joined_startups, members_for_startup, primary_startup, sent_pending_invites


def _stuck_level(days: int | None) -> str:
    if days is None:
        return "none"
    if days >= 7:
        return "critical"
    if days >= 3:
        return "warn"
    return "none"


def admin_startup_progress(startup: Startup) -> dict:
    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    current = step_at(startup.roadmap_step, steps)
    members = members_for_startup(startup)
    pending = sent_pending_invites(startup)
    days = None if progress["finished"] else days_on_current_step(startup, steps)
    weekly = weekly_goals_summary(startup) if not progress["finished"] else None
    logs = sorted(
        step_logs_by_index(startup).values(),
        key=lambda item: item.completed_at,
    )
    too = too_status(startup, steps, step_logs_by_index(startup))
    return {
        "startup": startup,
        "progress": progress,
        "current_label": current.get("label", "—"),
        "step_index": startup.roadmap_step if not progress["finished"] else None,
        "members": members,
        "member_count": len(members),
        "pending_invites": pending,
        "days_on_step": days,
        "stuck_level": _stuck_level(days),
        "weekly_goals_done": weekly["done"] if weekly else None,
        "weekly_goals_total": weekly["total"] if weekly else None,
        "step_logs": logs,
        "too": too,
    }


def admin_retention_row(user: User) -> dict | None:
    if is_investor(user):
        return None
    startup = primary_startup(user)
    if not startup:
        return None
    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    if progress["finished"]:
        too = too_status(startup, steps, step_logs_by_index(startup))
        return {
            "user": user,
            "startup": startup,
            "step_index": None,
            "step_label": "Завершено",
            "progress_pct": 100,
            "days_on_step": None,
            "stuck_level": "none",
            "progress": progress,
            "too": too,
        }
    days = days_on_current_step(startup, steps)
    current = step_at(startup.roadmap_step, steps)
    too = too_status(startup, steps, step_logs_by_index(startup))
    return {
        "user": user,
        "startup": startup,
        "step_index": startup.roadmap_step,
        "step_label": current.get("label", "—"),
        "progress_pct": progress["percent"],
        "days_on_step": days,
        "stuck_level": _stuck_level(days),
        "progress": progress,
        "too": too,
    }


def admin_user_progress_summary(user: User) -> str:
    row = admin_retention_row(user)
    if not row:
        return "—"
    p = row["progress"]
    return f"{p['done']}/{p['total']} · {p['percent']}%"


def admin_user_stuck_summary(user: User) -> dict:
    row = admin_retention_row(user)
    if not row or row["days_on_step"] is None:
        return {"label": "—", "level": "none"}
    days = row["days_on_step"]
    if days >= 7:
        return {"label": f"{days} дн.", "level": "critical", "badge": "7+"}
    if days >= 3:
        return {"label": f"{days} дн.", "level": "warn"}
    return {"label": f"{days} дн.", "level": "none"}


def admin_user_step_summary(user: User) -> str:
    row = admin_retention_row(user)
    if not row:
        return "—"
    base = f"{row['progress']['done']}/{row['progress']['total']} · {row['step_label'][:28]}"
    if row["days_on_step"] is not None and row["days_on_step"] >= 3:
        return f"{base} · застрял {row['days_on_step']} дн."
    return base


def admin_user_team_summary(user: User) -> str:
    startup = primary_startup(user)
    if not startup:
        joined = joined_startups(user)
        if joined:
            return f"в {len(joined)} ком."
        return "—"
    count = len(members_for_startup(startup))
    if count <= 1:
        return "—"
    return f"{count} чел."


def admin_stuck_founders(min_days: int = 7) -> list[dict]:
    rows = []
    users = User.query.filter(User.account_type != ACCOUNT_INVESTOR).order_by(User.id.desc()).all()
    for user in users:
        row = admin_retention_row(user)
        if not row or row["days_on_step"] is None:
            continue
        if row["days_on_step"] >= min_days:
            rows.append(row)
    rows.sort(key=lambda item: item["days_on_step"] or 0, reverse=True)
    return rows


def admin_onboarding_funnel() -> list[dict]:
    rows = []
    users = User.query.filter(
        User.account_type != ACCOUNT_INVESTOR,
        User.onboarding_done.is_(True),
    ).order_by(User.id.desc()).all()
    for user in users:
        checklist = onboarding_task_status(user)
        if not checklist:
            continue
        missing = [task["label"] for task in checklist["tasks"] if not task["done"]]
        has_project = has_ai_validated_startup(user)
        rows.append(
            {
                "user": user,
                "done_count": checklist["done_count"],
                "total": checklist["total"],
                "missing": missing,
                "has_ai_project": has_project,
            }
        )
    return rows


def admin_retention_stats() -> dict:
    unread = Notification.query.filter(Notification.read_at.is_(None)).count()
    push_subs = PushSubscription.query.count()
    stuck = len(admin_stuck_founders(min_days=7))
    incomplete = len(admin_onboarding_funnel())
    return {
        "unread_notifications": unread,
        "push_subscriptions": push_subs,
        "stuck_founders": stuck,
        "incomplete_onboarding": incomplete,
    }


def admin_user_retention_detail(user: User) -> dict | None:
    if is_investor(user):
        return None
    row = admin_retention_row(user)
    checklist = onboarding_checklist(user)
    push_count = PushSubscription.query.filter_by(user_id=user.id).count()
    startup = primary_startup(user)
    weekly = weekly_goals_summary(startup) if startup else None
    return {
        "retention_row": row,
        "checklist": checklist,
        "push_count": push_count,
        "weekly_goals": weekly,
    }


def admin_user_detail(user: User) -> dict:
    owned = Startup.query.filter_by(owner_id=user.id).order_by(Startup.id.desc()).all()
    owned_rows = [admin_startup_progress(s) for s in owned]
    joined_rows = [admin_startup_progress(s) for s in joined_startups(user)]

    invites_sent = (
        TeamInvitation.query.filter_by(inviter_id=user.id)
        .order_by(TeamInvitation.created_at.desc())
        .limit(20)
        .all()
    )
    invites_received = (
        TeamInvitation.query.filter_by(invitee_id=user.id)
        .order_by(TeamInvitation.created_at.desc())
        .limit(20)
        .all()
    )

    activities = (
        Activity.query.filter_by(user_id=user.id)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(40)
        .all()
    )
    likes_count = ActivityLike.query.filter_by(user_id=user.id).count()
    comments_count = ActivityComment.query.filter_by(user_id=user.id).count()
    threads = (
        AiThread.query.filter_by(user_id=user.id)
        .order_by(AiThread.updated_at.desc())
        .limit(15)
        .all()
    )
    notifications = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(25)
        .all()
    )

    return {
        "owned_startups": owned_rows,
        "joined_startups": joined_rows,
        "invites_sent": invites_sent,
        "invites_received": invites_received,
        "activities": activities,
        "likes_count": likes_count,
        "comments_count": comments_count,
        "threads": threads,
        "notifications": notifications,
    }


def admin_teams_overview() -> list[dict]:
    startups = Startup.query.order_by(Startup.name.asc()).all()
    rows = []
    for startup in startups:
        members = members_for_startup(startup)
        pending = sent_pending_invites(startup)
        if len(members) <= 1 and not pending:
            continue
        row = admin_startup_progress(startup)
        rows.append(row)
    return rows


def admin_recent_invitations(limit: int = 30) -> list[TeamInvitation]:
    return (
        TeamInvitation.query.order_by(TeamInvitation.created_at.desc())
        .limit(limit)
        .all()
    )


def admin_interaction_stats() -> dict:
    by_kind = dict(
        db.session.query(Activity.kind, func.count(Activity.id))
        .group_by(Activity.kind)
        .all()
    )
    return {
        "likes": ActivityLike.query.count(),
        "comments": ActivityComment.query.count(),
        "by_kind": by_kind,
    }
