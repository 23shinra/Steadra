from sqlalchemy import func

from ..models import db
from ..models.entities import Activity, ActivityComment, ActivityLike, ActivityReaction, Startup, User
from .idea_poll import poll_bundle, poll_for_activity
from .team import feed_invite_meta


def startup_for_feed_post(user: User) -> Startup | None:
    startup = (
        Startup.query.filter_by(owner_id=user.id).order_by(Startup.id.desc()).first()
    )
    if startup:
        return startup
    startup = Startup(
        name=f"{user.name} · лента",
        tagline="Личные посты",
        stage="Idea",
        owner_id=user.id,
    )
    db.session.add(startup)
    db.session.flush()
    return startup


def feed_items_for(activities: list[Activity], user: User | None) -> list[dict]:
    if not activities:
        return []
    ids = [a.id for a in activities]
    counts = dict(
        db.session.query(ActivityLike.activity_id, func.count(ActivityLike.id))
        .filter(ActivityLike.activity_id.in_(ids))
        .group_by(ActivityLike.activity_id)
        .all()
    )
    liked_ids: set[int] = set()
    if user:
        liked_ids = {
            row[0]
            for row in db.session.query(ActivityLike.activity_id)
            .filter(ActivityLike.user_id == user.id, ActivityLike.activity_id.in_(ids))
            .all()
        }
    comments = (
        ActivityComment.query.filter(ActivityComment.activity_id.in_(ids))
        .order_by(ActivityComment.created_at.asc())
        .all()
    )
    comments_by_activity: dict[int, list[ActivityComment]] = {}
    for comment in comments:
        comments_by_activity.setdefault(comment.activity_id, []).append(comment)

    reaction_counts: dict[int, dict[str, int]] = {}
    reaction_rows = (
        db.session.query(ActivityReaction.activity_id, ActivityReaction.reaction, func.count(ActivityReaction.id))
        .filter(ActivityReaction.activity_id.in_(ids))
        .group_by(ActivityReaction.activity_id, ActivityReaction.reaction)
        .all()
    )
    for activity_id, reaction, count in reaction_rows:
        reaction_counts.setdefault(activity_id, {})[reaction] = count

    user_reactions: dict[int, set[str]] = {}
    if user:
        for activity_id, reaction in (
            db.session.query(ActivityReaction.activity_id, ActivityReaction.reaction)
            .filter(ActivityReaction.user_id == user.id, ActivityReaction.activity_id.in_(ids))
            .all()
        ):
            user_reactions.setdefault(activity_id, set()).add(reaction)

    items = []
    for activity in activities:
        invite_meta = feed_invite_meta(user, activity.user)
        poll_data = None
        if activity.kind == "poll":
            poll = poll_for_activity(activity.id)
            if poll:
                poll_data = poll_bundle(poll, user)
        items.append(
            {
                "activity": activity,
                "likes_count": counts.get(activity.id, 0),
                "liked": activity.id in liked_ids,
                "comments": comments_by_activity.get(activity.id, []),
                "reaction_counts": reaction_counts.get(activity.id, {}),
                "user_reactions": user_reactions.get(activity.id, set()),
                "poll": poll_data,
                "can_invite": invite_meta["can_invite"],
                "invite_status": invite_meta["invite_status"],
                "invite_startup": invite_meta["invite_startup"],
            }
        )
    return items
