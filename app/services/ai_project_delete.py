from __future__ import annotations

import re
from pathlib import Path

from flask import current_app

from ..models import db
from ..models.entities import (
    Activity,
    AiThread,
    IdeaPoll,
    InvestorDealStatus,
    InvestorFavorite,
    RoadmapStepLog,
    Startup,
    StartupDocument,
    StepValidationRequest,
    StepWeeklyGoal,
    TooValidationRequest,
    User,
)
from .ai_threads import resolve_thread

DELETE_INTENT_RE = re.compile(
    r"^\s*(?:"
    r"уб(?:ить|ери)\s+(?:этот\s+)?(?:проект|идею|чат|стартап|диалог)"
    r"|удали(?:ть)?\s+(?:этот\s+)?(?:проект|идею|чат|стартап|диалог)"
    r"|закры(?:ть|й)\s+(?:этот\s+)?(?:проект|идею|чат|стартап)"
    r"|снес(?:ти|и)\s+(?:этот\s+)?(?:проект|идею|чат|стартап)"
    r"|kill\s+(?:this\s+)?(?:project|startup|idea)"
    r"|delete\s+(?:this\s+)?(?:project|startup|idea|chat)"
    r")\s*[.!?…]*\s*$",
    re.IGNORECASE,
)

CONFIRM_DELETE_RE = re.compile(
    r"^\s*(?:"
    r"да[,\s]+удал(?:ить|и|яй)"
    r"|подтверждаю(?:\s+удаление)?"
    r"|удал(?:и|яй)(?:\s+проект)?"
    r"|yes[,\s]+delete"
    r")\s*[.!?…]*\s*$",
    re.IGNORECASE,
)

CANCEL_DELETE_RE = re.compile(
    r"^\s*(?:"
    r"отмена"
    r"|не\s+удал(?:ять|яй|и)"
    r"|остав(?:ь|ить)(?:\s+проект)?"
    r"|cancel"
    r")\s*[.!?…]*\s*$",
    re.IGNORECASE,
)

PENDING_DELETE_SESSION_KEY = "pending_delete_thread_id"


def is_delete_intent(message: str) -> bool:
    return bool(DELETE_INTENT_RE.match((message or "").strip()))


def is_delete_confirm(message: str) -> bool:
    return bool(CONFIRM_DELETE_RE.match((message or "").strip()))


def is_delete_cancel(message: str) -> bool:
    return bool(CANCEL_DELETE_RE.match((message or "").strip()))


def project_label(thread: AiThread) -> str:
    if thread.startup_id:
        startup = db.session.get(Startup, thread.startup_id)
        if startup:
            return startup.name
    return thread.title or "этот проект"


def _remove_document_files(docs: list[StartupDocument]) -> None:
    from ..security import path_is_under

    root = Path(current_app.config.get("DOCUMENTS_FOLDER", "uploads/documents"))
    if not root.is_absolute():
        root = Path(current_app.root_path).parent / root
    for doc in docs:
        path = Path(doc.filepath)
        if path_is_under(root, path) and path.is_file():
            try:
                path.unlink()
            except OSError:
                current_app.logger.warning("Could not delete document file %s", doc.id)


def _delete_startup(startup: Startup) -> None:
    startup_id = startup.id

    polls = IdeaPoll.query.filter_by(startup_id=startup_id).all()
    activity_ids = {poll.activity_id for poll in polls}
    for poll in polls:
        db.session.delete(poll)
    db.session.flush()

    for activity_id in activity_ids:
        activity = db.session.get(Activity, activity_id)
        if activity:
            db.session.delete(activity)

    Activity.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)
    RoadmapStepLog.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)
    StepValidationRequest.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)
    TooValidationRequest.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)
    StepWeeklyGoal.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)

    docs = StartupDocument.query.filter_by(startup_id=startup_id).all()
    _remove_document_files(docs)
    for doc in docs:
        db.session.delete(doc)

    InvestorFavorite.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)
    InvestorDealStatus.query.filter_by(startup_id=startup_id).delete(synchronize_session=False)

    for thread in AiThread.query.filter_by(startup_id=startup_id).all():
        db.session.delete(thread)

    User.query.filter(User.active_startup_id == startup_id).update(
        {User.active_startup_id: None},
        synchronize_session=False,
    )
    db.session.delete(startup)


def delete_thread_project(user: User, thread: AiThread) -> str:
    if thread.user_id != user.id:
        raise PermissionError("Нет доступа к этому чату.")

    label = project_label(thread)
    startup = db.session.get(Startup, thread.startup_id) if thread.startup_id else None

    if startup:
        if startup.owner_id != user.id:
            raise PermissionError("Нет доступа к этому проекту.")
        _delete_startup(startup)
    else:
        db.session.delete(thread)

    db.session.commit()
    return label
