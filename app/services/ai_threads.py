from datetime import datetime, timezone

from ..models import db
from ..models.entities import AiMessage, AiThread, User


def threads_for_user(user: User) -> list[AiThread]:
    return (
        AiThread.query.filter_by(user_id=user.id)
        .filter(AiThread.messages.any())
        .order_by(AiThread.updated_at.desc(), AiThread.id.desc())
        .all()
    )


def resolve_thread(user: User, thread_id: int | None) -> AiThread | None:
    if not thread_id:
        return None
    return AiThread.query.filter_by(id=thread_id, user_id=user.id).first()


def update_thread_summary(thread: AiThread, title: str) -> None:
    thread.title = title
    thread.updated_at = datetime.now(timezone.utc)
    db.session.add(thread)
    db.session.commit()


def create_thread(user: User, title: str = "Новый чат") -> AiThread:
    now = datetime.now(timezone.utc)
    thread = AiThread(user_id=user.id, title=title, created_at=now, updated_at=now)
    db.session.add(thread)
    db.session.commit()
    return thread


def history_for_thread(thread: AiThread, limit: int = 40) -> list[dict]:
    messages = (
        AiMessage.query.filter_by(thread_id=thread.id)
        .order_by(AiMessage.created_at.asc(), AiMessage.id.asc())
        .limit(limit)
        .all()
    )
    return [{"role": message.role, "content": message.content} for message in messages]


def add_message(thread: AiThread, role: str, content: str) -> AiMessage:
    message = AiMessage(thread_id=thread.id, role=role, content=content)
    thread.updated_at = datetime.now(timezone.utc)
    db.session.add(message)
    db.session.add(thread)
    db.session.commit()
    return message
