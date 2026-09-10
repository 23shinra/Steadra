from __future__ import annotations

import json
from typing import Any

from flask import current_app

_redis_client = None


def _utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _as_utc(dt):
    from datetime import timezone

    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_redis():
    global _redis_client
    url = current_app.config.get("REDIS_URL", "")
    if not url:
        return None
    if _redis_client is None:
        try:
            import redis

            _redis_client = redis.from_url(url, decode_responses=True)
            _redis_client.ping()
        except Exception:
            current_app.logger.warning("Redis unavailable, falling back to DB")
            _redis_client = False
    return _redis_client if _redis_client is not False else None


def cache_set(key: str, value: str, ttl: int = 300) -> None:
    client = get_redis()
    if client:
        client.setex(key, ttl, value)
        return
    from datetime import datetime, timedelta, timezone

    from ..models import db
    from ..models.entities import CacheEntry

    entry = CacheEntry.query.filter_by(key=key).first()
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    if not entry:
        entry = CacheEntry(key=key, value=value, expires_at=expires)
        db.session.add(entry)
    else:
        entry.value = value
        entry.expires_at = expires
    db.session.commit()


def cache_get(key: str) -> str | None:
    client = get_redis()
    if client:
        return client.get(key)
    from ..models.entities import CacheEntry

    entry = CacheEntry.query.filter_by(key=key).first()
    if not entry:
        return None
    if entry.expires_at and _as_utc(entry.expires_at) < _utc_now():
        from ..models import db

        db.session.delete(entry)
        db.session.commit()
        return None
    return entry.value


def cache_delete(key: str) -> None:
    client = get_redis()
    if client:
        client.delete(key)
        return
    from ..models import db
    from ..models.entities import CacheEntry

    CacheEntry.query.filter_by(key=key).delete()
    db.session.commit()


def cache_incr(key: str, ttl: int = 300) -> int:
    """Atomic-ish counter with TTL. Returns new value after increment."""
    client = get_redis()
    if client:
        value = int(client.incr(key))
        if value == 1:
            client.expire(key, ttl)
        return value

    from datetime import datetime, timedelta, timezone

    from ..models import db
    from ..models.entities import CacheEntry

    now = datetime.now(timezone.utc)
    entry = CacheEntry.query.filter_by(key=key).first()
    if entry and entry.expires_at and _as_utc(entry.expires_at) < now:
        db.session.delete(entry)
        db.session.commit()
        entry = None
    if not entry:
        entry = CacheEntry(
            key=key,
            value="1",
            expires_at=now + timedelta(seconds=ttl),
        )
        db.session.add(entry)
        db.session.commit()
        return 1
    try:
        value = int(entry.value or "0") + 1
    except (TypeError, ValueError):
        value = 1
    entry.value = str(value)
    db.session.add(entry)
    db.session.commit()
    return value


def cache_set_json(key: str, data: Any, ttl: int = 300) -> None:
    cache_set(key, json.dumps(data, ensure_ascii=False), ttl=ttl)


def cache_get_json(key: str) -> Any | None:
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
