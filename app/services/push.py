import json
import logging

from flask import current_app

from ..models import db
from ..models.entities import PushSubscription

logger = logging.getLogger(__name__)


def save_subscription(user, payload: dict) -> PushSubscription | None:
    endpoint = (payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return None

    existing = PushSubscription.query.filter_by(user_id=user.id, endpoint=endpoint).first()
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        db.session.add(existing)
        db.session.commit()
        return existing

    sub = PushSubscription(user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth)
    db.session.add(sub)
    db.session.commit()
    return sub


def send_push(user, title: str, body: str, url: str = "/app") -> None:
    private_key = current_app.config.get("VAPID_PRIVATE_KEY")
    public_key = current_app.config.get("VAPID_PUBLIC_KEY")
    if not private_key or not public_key:
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed")
        return

    claims = {"sub": current_app.config.get("VAPID_CLAIMS_EMAIL", "mailto:admin@kangaroo.kz")}
    payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    subs = PushSubscription.query.filter_by(user_id=user.id).all()
    dead = []

    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims=claims,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                dead.append(sub)
            else:
                logger.warning("push failed for user %s: %s", user.id, exc)

    for sub in dead:
        db.session.delete(sub)
    if dead:
        db.session.commit()
