from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func

from ..models import db
from ..models.entities import Activity, ActivityComment, ActivityLike, ActivityReaction, IdeaPoll, IdeaPollVote, Startup, User

VERDICT_LABELS = {
    IdeaPoll.VERDICT_PENDING: "Собираем отклики…",
    IdeaPoll.VERDICT_GOOD: "Норм тема",
    IdeaPoll.VERDICT_UNCLEAR: "Нужно больше данных",
    IdeaPoll.VERDICT_WEAK: "Слабая тема",
}

MIN_VOTES_FOR_VERDICT = 3
MIN_ENGAGEMENT_FOR_VERDICT = 5


def create_idea_poll(user: User, startup: Startup, hypothesis: str, title: str | None = None) -> IdeaPoll:
    hypothesis = hypothesis.strip()
    if len(hypothesis) < 10:
        raise ValueError("Гипотеза слишком короткая")
    headline = (title or f"Опрос: {startup.name}").strip()[:160]
    body = (
        f"Гипотеза: {hypothesis}\n\n"
        "Голосуй — помоги фаундеру понять, стоит ли идти дальше.\n"
        "👍 Да, актуально · 🤔 Не уверен · 👎 Нет"
    )
    activity = Activity(
        kind="poll",
        title=headline,
        body=body,
        impact=5,
        user_id=user.id,
        startup_id=startup.id,
    )
    db.session.add(activity)
    db.session.flush()
    poll = IdeaPoll(
        startup_id=startup.id,
        activity_id=activity.id,
        user_id=user.id,
        hypothesis=hypothesis,
    )
    db.session.add(poll)
    db.session.commit()
    _maybe_advance_poll_step(startup.id)
    return poll


def poll_for_activity(activity_id: int) -> IdeaPoll | None:
    return IdeaPoll.query.filter_by(activity_id=activity_id).first()


def poll_for_startup(startup_id: int) -> IdeaPoll | None:
    return IdeaPoll.query.filter_by(startup_id=startup_id).order_by(IdeaPoll.created_at.desc()).first()


def user_vote(poll: IdeaPoll, user_id: int) -> str | None:
    row = IdeaPollVote.query.filter_by(poll_id=poll.id, user_id=user_id).first()
    return row.choice if row else None


def cast_vote(poll: IdeaPoll, user: User, choice: str) -> IdeaPoll:
    if choice not in {IdeaPollVote.CHOICE_YES, IdeaPollVote.CHOICE_NO, IdeaPollVote.CHOICE_MAYBE}:
        raise ValueError("Неверный голос")
    if user.id == poll.user_id:
        raise ValueError("Автор не голосует в своём опросе")
    existing = IdeaPollVote.query.filter_by(poll_id=poll.id, user_id=user.id).first()
    if existing:
        existing.choice = choice
    else:
        db.session.add(IdeaPollVote(poll_id=poll.id, user_id=user.id, choice=choice))
    db.session.commit()
    return refresh_poll_score(poll)


def _engagement_for_activity(activity_id: int) -> int:
    likes = ActivityLike.query.filter_by(activity_id=activity_id).count()
    comments = ActivityComment.query.filter_by(activity_id=activity_id).count()
    reactions = ActivityReaction.query.filter_by(activity_id=activity_id).count()
    return likes + comments + reactions


def refresh_poll_score(poll: IdeaPoll) -> IdeaPoll:
    votes = IdeaPollVote.query.filter_by(poll_id=poll.id).all()
    yes = sum(1 for v in votes if v.choice == IdeaPollVote.CHOICE_YES)
    no = sum(1 for v in votes if v.choice == IdeaPollVote.CHOICE_NO)
    maybe = sum(1 for v in votes if v.choice == IdeaPollVote.CHOICE_MAYBE)
    total_votes = yes + no + maybe
    engagement = _engagement_for_activity(poll.activity_id)

    vote_weight = yes * 5 + maybe * 2 - no * 3
    max_vote_weight = max(total_votes * 5, 1)
    vote_pct = max(0, min(100, int(50 + (vote_weight / max_vote_weight) * 50)))

    engage_bonus = min(30, engagement * 3)
    score = min(100, max(0, int(vote_pct * 0.75 + engage_bonus)))

    poll.yes_count = yes
    poll.no_count = no
    poll.maybe_count = maybe
    poll.engagement_count = engagement + total_votes
    poll.score = score
    poll.computed_at = datetime.now(timezone.utc)

    if total_votes < MIN_VOTES_FOR_VERDICT and poll.engagement_count < MIN_ENGAGEMENT_FOR_VERDICT:
        poll.verdict = IdeaPoll.VERDICT_PENDING
    elif yes >= no * 1.5 and score >= 55:
        poll.verdict = IdeaPoll.VERDICT_GOOD
    elif no > yes and total_votes >= MIN_VOTES_FOR_VERDICT:
        poll.verdict = IdeaPoll.VERDICT_WEAK
    elif score >= 40:
        poll.verdict = IdeaPoll.VERDICT_UNCLEAR
    else:
        poll.verdict = IdeaPoll.VERDICT_WEAK

    db.session.add(poll)
    db.session.commit()
    _maybe_advance_poll_step(poll.startup_id)
    return poll


def _maybe_advance_poll_step(startup_id: int) -> None:
    try:
        from .step_validation import try_advance_poll_validation

        try_advance_poll_validation(startup_id)
    except Exception:
        pass


def poll_bundle(poll: IdeaPoll, viewer: User | None) -> dict:
    return {
        "poll": poll,
        "verdict_label": VERDICT_LABELS.get(poll.verdict, poll.verdict),
        "user_vote": user_vote(poll, viewer.id) if viewer else None,
        "total_votes": poll.yes_count + poll.no_count + poll.maybe_count,
    }
