from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from ..models import db


def _reset_if_needed(user) -> None:
    now = datetime.now(timezone.utc)
    reset_at = user.ai_requests_reset_at
    if reset_at and reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    if not reset_at or (now - reset_at).days >= 30:
        user.ai_requests_count = 0
        user.ai_requests_reset_at = now
        db.session.add(user)
        db.session.commit()


def ai_limit_for(user) -> int:
    if getattr(user, "is_premium", False):
        return int(current_app.config.get("AI_PREMIUM_MONTHLY_LIMIT", 9999))
    return int(current_app.config.get("AI_FREE_MONTHLY_LIMIT", 30))


def ai_remaining(user) -> int:
    _reset_if_needed(user)
    return max(0, ai_limit_for(user) - (user.ai_requests_count or 0))


def can_use_ai(user) -> bool:
    return ai_remaining(user) > 0


def consume_ai_request(user) -> bool:
    _reset_if_needed(user)
    if user.ai_requests_count >= ai_limit_for(user):
        return False
    user.ai_requests_count = (user.ai_requests_count or 0) + 1
    db.session.add(user)
    db.session.commit()
    return True
