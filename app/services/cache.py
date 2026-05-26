from __future__ import annotations

import json
from typing import Any

from flask import current_app

_redis_client = None


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
    from datetime import datetime, timezone

    entry = CacheEntry.query.filter_by(key=key).first()
    if not entry:
        return None
    if entry.expires_at and entry.expires_at < datetime.now(timezone.utc):
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
