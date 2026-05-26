from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from ..models import db
from ..models.entities import AnalyticsEvent


def track(event: str, user=None, **meta) -> None:
    if not current_app.config.get("ANALYTICS_ENABLED"):
        return
    try:
        import json

        db.session.add(
            AnalyticsEvent(
                user_id=user.id if user else None,
                event=event[:80],
                meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("analytics track failed")


def count_events(event: str, since: datetime | None = None) -> int:
    q = AnalyticsEvent.query.filter_by(event=event)
    if since:
        q = q.filter(AnalyticsEvent.created_at >= since)
    return q.count()
