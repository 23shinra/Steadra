from __future__ import annotations

from ..models import db
from ..models.entities import DirectMessage, User
from sqlalchemy import and_, or_


def send_message(sender: User, recipient_id: int, body: str) -> tuple[DirectMessage | None, str | None]:
    body = (body or "").strip()
    if len(body) < 1:
        return None, "Напиши сообщение."
    if len(body) > 900:
        return None, "Слишком длинное сообщение."
    recipient = db.session.get(User, recipient_id)
    if not recipient:
        return None, "Пользователь не найден."
    if recipient.id == sender.id:
        return None, "Нельзя написать самому себе."
    if not getattr(recipient, "open_for_messages", True):
        return None, "Пользователь закрыл личные сообщения."
    msg = DirectMessage(sender_id=sender.id, recipient_id=recipient.id, body=body)
    db.session.add(msg)
    db.session.commit()
    return msg, None


def conversation(user: User, other_id: int, limit: int = 50) -> list[DirectMessage]:
    return (
        DirectMessage.query.filter(
            or_(
                and_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == other_id),
                and_(DirectMessage.sender_id == other_id, DirectMessage.recipient_id == user.id),
            )
        )
        .order_by(DirectMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def inbox(user: User) -> list[dict]:
    from sqlalchemy import func

    sub = (
        db.session.query(
            DirectMessage.recipient_id,
            DirectMessage.sender_id,
            func.max(DirectMessage.created_at).label("last_at"),
        )
        .filter(
            or_(DirectMessage.sender_id == user.id, DirectMessage.recipient_id == user.id)
        )
        .group_by(DirectMessage.recipient_id, DirectMessage.sender_id)
        .subquery()
    )
    messages = DirectMessage.query.order_by(DirectMessage.created_at.desc()).limit(100).all()
    seen = set()
    threads = []
    for msg in messages:
        if msg.sender_id != user.id and msg.recipient_id != user.id:
            continue
        other_id = msg.recipient_id if msg.sender_id == user.id else msg.sender_id
        if other_id in seen:
            continue
        seen.add(other_id)
        other = db.session.get(User, other_id)
        unread = DirectMessage.query.filter_by(
            sender_id=other_id, recipient_id=user.id
        ).filter(DirectMessage.read_at.is_(None)).count()
        threads.append({"other": other, "last": msg, "unread": unread})
    return threads


def mark_read(user: User, other_id: int) -> None:
    from datetime import datetime, timezone

    DirectMessage.query.filter_by(sender_id=other_id, recipient_id=user.id).filter(
        DirectMessage.read_at.is_(None)
    ).update({"read_at": datetime.now(timezone.utc)})
    db.session.commit()
