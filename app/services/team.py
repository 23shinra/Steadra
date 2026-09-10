from datetime import datetime, timezone

from ..access import ACCOUNT_INVESTOR, is_investor
from ..models import db
from ..models.entities import Activity, Startup, TeamInvitation, TeamMember, User
from .investor import team_detail
from .roadmap import (
    branch_map_state,
    days_on_current_step,
    is_finished,
    progress_stats,
    step_at,
    step_logs_by_index,
    step_timeline,
    steps_for_startup,
)
from .step_goals import ensure_weekly_goals


def is_founder(user: User | None) -> bool:
    return bool(user and not is_investor(user))


def primary_startup(user: User | None) -> Startup | None:
    if not user:
        return None
    return Startup.query.filter_by(owner_id=user.id).order_by(Startup.id.desc()).first()


def is_team_member(startup_id: int, user_id: int) -> bool:
    return (
        TeamMember.query.filter_by(startup_id=startup_id, user_id=user_id).first() is not None
    )


def pending_invite(startup_id: int, invitee_id: int) -> TeamInvitation | None:
    return TeamInvitation.query.filter_by(
        startup_id=startup_id,
        invitee_id=invitee_id,
        status=TeamInvitation.STATUS_PENDING,
    ).first()


def invite_state(viewer: User | None, invitee: User, startup: Startup | None) -> str:
    if not viewer or not is_founder(viewer) or not is_founder(invitee):
        return "hidden"
    if viewer.id == invitee.id:
        return "self"
    if not startup:
        return "no_startup"
    if is_team_member(startup.id, invitee.id):
        return "member"
    if pending_invite(startup.id, invitee.id):
        return "pending"
    return "ready"


def feed_invite_meta(viewer: User | None, author: User) -> dict:
    startup = primary_startup(viewer) if viewer else None
    state = invite_state(viewer, author, startup)
    return {
        "can_invite": state == "ready",
        "invite_status": state,
        "invite_startup": startup,
    }


def send_invite(inviter: User, invitee_id: int, startup_id: int | None = None) -> tuple[TeamInvitation | None, str | None]:
    if not is_founder(inviter):
        return None, "Приглашать могут только основатели."
    invitee = db.session.get(User, invitee_id)
    if not invitee:
        return None, "Пользователь не найден."
    if not is_founder(invitee):
        return None, "В команду можно приглашать только основателей."
    if inviter.id == invitee.id:
        return None, "Нельзя пригласить себя."
    startup = db.session.get(Startup, startup_id) if startup_id else primary_startup(inviter)
    if not startup or startup.owner_id != inviter.id:
        return None, "Сначала создай проект."
    if is_team_member(startup.id, invitee.id):
        return None, "Уже в команде."
    existing = pending_invite(startup.id, invitee.id)
    if existing:
        return existing, None
    invite = TeamInvitation(
        startup_id=startup.id,
        inviter_id=inviter.id,
        invitee_id=invitee.id,
        status=TeamInvitation.STATUS_PENDING,
    )
    db.session.add(invite)
    db.session.commit()
    from flask import current_app

    try:
        from .notifications import notify_team_invite

        notify_team_invite(invitee, inviter, startup, invite.id)
    except Exception:
        current_app.logger.exception("team invite notify failed")
    return invite, None


def accept_invite(invite: TeamInvitation, user: User) -> tuple[TeamMember | None, str | None]:
    if invite.invitee_id != user.id:
        return None, "Это приглашение не для вас."
    if invite.status != TeamInvitation.STATUS_PENDING:
        return None, "Приглашение уже обработано."
    if is_team_member(invite.startup_id, user.id):
        invite.status = TeamInvitation.STATUS_ACCEPTED
        invite.responded_at = datetime.now(timezone.utc)
        db.session.commit()
        return None, "Вы уже в этой команде."
    member = TeamMember(
        startup_id=invite.startup_id,
        user_id=user.id,
        team_role=_team_role_from_user(user),
    )
    invite.status = TeamInvitation.STATUS_ACCEPTED
    invite.responded_at = datetime.now(timezone.utc)
    db.session.add(member)
    startup = invite.startup
    inviter = invite.inviter
    db.session.add(
        Activity(
            kind="team",
            title=f"{user.name} в команде",
            body=f"{user.name} принял(а) приглашение в «{startup.name}» от {inviter.name}.",
            impact=3,
            user_id=user.id,
            startup_id=startup.id,
        )
    )
    db.session.commit()
    return member, None


def decline_invite(invite: TeamInvitation, user: User) -> str | None:
    if invite.invitee_id != user.id:
        return "Это приглашение не для вас."
    if invite.status != TeamInvitation.STATUS_PENDING:
        return "Приглашение уже обработано."
    invite.status = TeamInvitation.STATUS_DECLINED
    invite.responded_at = datetime.now(timezone.utc)
    db.session.commit()
    return None


def _team_role_from_user(user: User) -> str:
    label = (getattr(user, "role", None) or "").lower()
    if any(x in label for x in ("cto", "ai", "билдер", "tech", "инженер", "разраб")):
        return "cto"
    if any(x in label for x in ("ceo", "founder", "основател", "product", "продукт")):
        return "ceo"
    if any(x in label for x in ("market", "growth", "маркетинг")):
        return "marketing"
    return "member"


def members_for_startup(startup: Startup) -> list[User]:
    return [row["user"] for row in team_detail(startup)["members"]]


def member_rows_for_startup(startup: Startup) -> list[dict]:
    return team_detail(startup)["members"]


def pending_invites_for_user(user: User) -> list[TeamInvitation]:
    return (
        TeamInvitation.query.filter_by(
            invitee_id=user.id,
            status=TeamInvitation.STATUS_PENDING,
        )
        .order_by(TeamInvitation.created_at.desc())
        .all()
    )


def sent_pending_invites(startup: Startup) -> list[TeamInvitation]:
    return (
        TeamInvitation.query.filter_by(
            startup_id=startup.id,
            status=TeamInvitation.STATUS_PENDING,
        )
        .order_by(TeamInvitation.created_at.desc())
        .all()
    )


def joined_startups(user: User) -> list[Startup]:
    startup_ids = [row.startup_id for row in TeamMember.query.filter_by(user_id=user.id).all()]
    if not startup_ids:
        return []
    return Startup.query.filter(Startup.id.in_(startup_ids)).order_by(Startup.name.asc()).all()


def startup_team_profile(startup: Startup) -> dict:
    steps = steps_for_startup(startup)
    logs = step_logs_by_index(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    finished = is_finished(startup.roadmap_step, steps)
    current_step = None if finished else step_at(startup.roadmap_step, steps)
    days_on_step = days_on_current_step(startup, steps, logs) if current_step else None
    goals = ensure_weekly_goals(startup) if current_step else []
    weekly_goals = None
    if goals:
        done = sum(1 for g in goals if g.done)
        weekly_goals = {
            "goals": goals,
            "done": done,
            "total": len(goals),
            "all_done": done == len(goals),
        }
    timeline = [t for t in step_timeline(startup, steps, logs) if t["status"] in {"done", "active"}]
    return {
        "startup": startup,
        "owner": startup.owner,
        "steps": steps,
        "progress": progress,
        "current_step": current_step,
        "days_on_step": days_on_step,
        "weekly_goals": weekly_goals,
        "team": team_detail(startup),
        "map_nodes": branch_map_state(
            startup.roadmap_step,
            steps,
            logs,
            startup=startup,
            goals_done=weekly_goals["done"] if weekly_goals else 0,
        ),
        "step_timeline": timeline,
        "finished": finished,
    }


def invite_preview(invite: TeamInvitation) -> dict:
    profile = startup_team_profile(invite.startup)
    current = profile["current_step"]
    return {
        "invite": invite,
        "progress": profile["progress"],
        "current_step_label": current["label"] if current else "Ветка пройдена",
        "team_count": profile["team"]["count"],
        "days_on_step": profile["days_on_step"],
    }


def profile_team_context(profile_user: User, viewer: User | None) -> dict | None:
    if is_investor(profile_user):
        return None
    is_own = bool(viewer and viewer.id == profile_user.id)
    primary = primary_startup(profile_user) if is_own else None
    incoming = pending_invites_for_user(profile_user) if is_own else []
    invite_previews = [invite_preview(inv) for inv in incoming] if is_own else []
    members = members_for_startup(primary) if primary else []
    member_rows = member_rows_for_startup(primary) if primary else []
    sent = sent_pending_invites(primary) if primary else []
    joined = joined_startups(profile_user) if is_own else []
    return {
        "primary_startup": primary,
        "members": members,
        "member_rows": member_rows,
        "incoming_invites": incoming,
        "invite_previews": invite_previews,
        "sent_invites": sent,
        "joined_startups": joined,
        "incoming_count": len(incoming),
    }
