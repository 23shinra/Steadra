import json
import os
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from werkzeug.utils import secure_filename
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from ..access import is_investor
from ..models import db
from ..models.entities import Activity, ActivityReaction, Startup, StartupDocument, User
from ..routes.auth import session_user
from ..services.ai_agent import (
    analyze_fin_model,
    analyze_pitch_deck,
    describe_chat_image,
    describe_chat_video,
    generate_one_pager,
    generate_pitch_outline,
    generate_pitch_pre,
    generate_pitch_validated,
    generate_step_coach_turn,
)
from ..services.ai_limits import ai_remaining, can_use_ai, consume_ai_request
from ..services.analytics import track
from ..services.feed_social import feed_items_for
from ..services.idea_poll import cast_vote, create_idea_poll, refresh_poll_score
from ..services.investor_deal import get_deal, set_deal_status
from ..services.messages import conversation, inbox, mark_read, send_message
from ..services.partners import partners_for_step
from ..services.roadmap import progress_stats, step_at, steps_for_startup
from ..services.step_prompts import infer_step_key
from ..services.search import search_all
from ..services.step_goals import weekly_goals_summary

bp = Blueprint("extensions", __name__)


class IdeaPollForm(FlaskForm):
    hypothesis = TextAreaField("Гипотеза", validators=[DataRequired(), Length(min=10, max=500)])
    title = StringField("Заголовок", validators=[Optional(), Length(max=160)])


class PitchAnalyzeForm(FlaskForm):
    pitch_file = FileField(
        "Файл презентации",
        validators=[Optional(), FileAllowed(["pptx", "pdf", "txt"], "Нужен .pptx, .pdf или .txt")],
    )
    pitch_text = TextAreaField("Или текст слайдов", validators=[Optional(), Length(max=20000)])

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        has_file = bool(self.pitch_file.data and getattr(self.pitch_file.data, "filename", ""))
        has_text = bool((self.pitch_text.data or "").strip())
        if ok and not has_file and not has_text:
            self.pitch_file.errors += ("Загрузи .pptx/.pdf или вставь текст слайдов.",)
            return False
        return ok


class FinModelForm(FlaskForm):
    model_type = SelectField("Модель", choices=[("b2c", "B2C — людям"), ("b2b", "B2B — компаниям")], default="b2c")
    cac = StringField("CAC (стоимость привлечения)", validators=[Optional(), Length(max=120)])
    arpu = StringField("ARPU / средний чек", validators=[Optional(), Length(max=120)])
    retention = StringField("Retention / удержание", validators=[Optional(), Length(max=120)])
    ltv = StringField("LTV", validators=[Optional(), Length(max=120)])
    acv = StringField("ACV (годовой контракт B2B)", validators=[Optional(), Length(max=120)])
    sales_cycle = StringField("Sales cycle (дней)", validators=[Optional(), Length(max=120)])
    churn = StringField("Churn (% в месяц)", validators=[Optional(), Length(max=120)])
    margin = StringField("Gross margin (%)", validators=[Optional(), Length(max=120)])
    notes = TextAreaField("Дополнительно", validators=[Optional(), Length(max=900)])


class MessageForm(FlaskForm):
    body = TextAreaField("Сообщение", validators=[DataRequired(), Length(min=1, max=900)])


from ..routes.investor import DealForm


@bp.get("/search")
def search_page():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    q = request.args.get("q", "")
    kind = request.args.get("kind", "all")
    stage = request.args.get("stage", "")
    has_too = request.args.get("has_too") if is_investor(user) else None
    too_filter = None
    if is_investor(user):
        if has_too == "1":
            too_filter = True
        elif has_too == "0":
            too_filter = False
    results = search_all(q, kind=kind if kind != "all" else None, stage=stage or None, has_too=too_filter)
    track("search", user, query=q[:80])
    return render_template(
        "search.html",
        user=user,
        q=q,
        kind=kind,
        stage=stage,
        has_too=has_too or "",
        results=results,
        show_too_filter=is_investor(user),
        active_tab="search",
    )


@bp.get("/search/partial")
def search_partial():
    user = session_user()
    if not user:
        abort(401)
    q = request.args.get("q", "")
    results = search_all(q)
    return render_template("partials/search_results.html", results=results, q=q, is_investor_user=is_investor(user))


@bp.get("/messages")
def messages_inbox():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    return render_template(
        "messages/inbox.html",
        user=user,
        threads=inbox(user),
        active_tab="messages" if is_investor(user) else "profile",
    )


@bp.get("/messages/<int:other_id>")
def messages_thread(other_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    other = db.session.get(User, other_id) or abort(404)
    mark_read(user, other_id)
    return render_template(
        "messages/thread.html",
        user=user,
        other=other,
        messages=conversation(user, other_id),
        form=MessageForm(),
        active_tab="messages" if is_investor(user) else "profile",
    )


@bp.post("/messages/<int:other_id>")
def messages_send(other_id: int):
    user = session_user()
    if not user:
        abort(401)
    form = MessageForm()
    if not form.validate_on_submit():
        abort(422)
    msg, error = send_message(user, other_id, form.body.data)
    if error:
        return render_template("partials/message_error.html", error=error), 422
    track("dm_sent", user, to=other_id)
    return render_template("partials/message_bubble.html", msg=msg, viewer=user)


@bp.get("/partners")
def partners_page():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    step_key = request.args.get("step")
    region = getattr(user, "region", None)
    return render_template(
        "partners.html",
        user=user,
        partners=partners_for_step(step_key, region),
        active_tab="progress",
    )


@bp.post("/startup/<int:startup_id>/coach")
def step_coach(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    if not can_use_ai(user):
        return render_template("partials/chat_error.html", error="Лимит AI-запросов исчерпан."), 429
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    steps = steps_for_startup(startup)
    step = step_at(startup.roadmap_step, steps)
    weekly = weekly_goals_summary(startup)
    goals = [g["label"] for g in (weekly.get("goals") or []) if not g.get("done")]
    try:
        data = generate_step_coach_turn(
            user, startup.name, startup.tagline, step, startup.roadmap_step, len(steps), goals
        )
        consume_ai_request(user)
    except Exception:
        current_app.logger.exception("step coach failed")
        return render_template("partials/chat_error.html", error="AI временно недоступен."), 503
    track("step_coach", user, startup_id=startup_id)
    return render_template("partials/step_coach_reply.html", reply=data.get("reply", ""))


@bp.get("/startup/<int:startup_id>/one-pager")
def one_pager(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    if not can_use_ai(user):
        flash_msg = "Лимит AI исчерпан."
        return render_template("artifacts/one_pager.html", startup=startup, error=flash_msg, pager=None)
    try:
        pager = generate_one_pager(user, startup, steps, progress)
        consume_ai_request(user)
    except Exception:
        current_app.logger.exception("one-pager failed")
        pager = None
    track("one_pager", user, startup_id=startup_id)
    return render_template(
        "artifacts/one_pager.html",
        startup=startup,
        pager=pager,
        user=user,
        ai_remaining=ai_remaining(user),
    )


@bp.get("/startup/<int:startup_id>/pitch")
def pitch_outline(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    outline = None
    if can_use_ai(user):
        try:
            outline = generate_pitch_outline(user, startup, steps, progress)
            consume_ai_request(user)
        except Exception:
            current_app.logger.exception("pitch failed")
    track("pitch_outline", user, startup_id=startup_id)
    return render_template(
        "artifacts/pitch.html",
        startup=startup,
        outline=outline,
        user=user,
        ai_remaining=ai_remaining(user),
    )


@bp.get("/startup/<int:startup_id>/pitch/pre")
def pitch_pre(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    outline = None
    if can_use_ai(user):
        try:
            outline = generate_pitch_pre(user, startup, steps_for_startup(startup), progress_stats(startup.roadmap_step, steps_for_startup(startup)))
            startup.pitch_pre_json = json.dumps(outline, ensure_ascii=False)
            db.session.commit()
            consume_ai_request(user)
        except Exception:
            current_app.logger.exception("pitch pre failed")
    track("pitch_pre", user, startup_id=startup_id)
    return render_template(
        "artifacts/pitch.html",
        startup=startup,
        outline=outline,
        user=user,
        ai_remaining=ai_remaining(user),
        deck_stage="pre_mvp",
    )


@bp.get("/startup/<int:startup_id>/pitch/validated")
def pitch_validated(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    steps = steps_for_startup(startup)
    progress = progress_stats(startup.roadmap_step, steps)
    outline = None
    if can_use_ai(user):
        try:
            outline = generate_pitch_validated(user, startup, steps, progress)
            consume_ai_request(user)
        except Exception:
            current_app.logger.exception("pitch validated failed")
    track("pitch_validated", user, startup_id=startup_id)
    return render_template(
        "artifacts/pitch.html",
        startup=startup,
        outline=outline,
        user=user,
        ai_remaining=ai_remaining(user),
        deck_stage="validated",
    )


@bp.route("/startup/<int:startup_id>/pitch/analyze", methods=["GET", "POST"])
def pitch_analyze(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    form = PitchAnalyzeForm()
    analysis = None
    if startup.pitch_analysis_json:
        try:
            analysis = json.loads(startup.pitch_analysis_json)
        except json.JSONDecodeError:
            analysis = None
    if request.method == "POST" and form.validate_on_submit():
        if not can_use_ai(user):
            flash("Лимит AI исчерпан.", "error")
        else:
            from ..services.pitch_deck import PitchDeckError, extract_from_upload, extract_pasted_text

            previous = analysis if isinstance(analysis, dict) else None
            try:
                upload = form.pitch_file.data
                filename = ""
                source = "text"
                if upload and getattr(upload, "filename", ""):
                    slides = extract_from_upload(upload)
                    filename = (upload.filename or "")[:120]
                    source = "upload"
                else:
                    slides = extract_pasted_text(form.pitch_text.data or "")
                analysis = analyze_pitch_deck(
                    user, startup, slides, previous=previous, source=source, filename=filename
                )
                startup.pitch_analysis_json = json.dumps(analysis, ensure_ascii=False)
                db.session.commit()
                consume_ai_request(user)
                track("pitch_analyze", user, startup_id=startup_id, score=analysis.get("score"))
                from ..services.step_validation import maybe_complete_pitch_step

                maybe_complete_pitch_step(user, startup, analysis)
            except PitchDeckError as exc:
                flash(str(exc), "error")
            except Exception:
                current_app.logger.exception("pitch analyze failed")
                flash("AI временно недоступен.", "error")
    return render_template(
        "artifacts/pitch_analyze.html",
        startup=startup,
        form=form,
        analysis=analysis,
        user=user,
        ai_remaining=ai_remaining(user),
    )


@bp.post("/startup/<int:startup_id>/pitch/analyze/chat")
@bp.post("/startup/<int:startup_id>/chat/attach")
def pitch_analyze_chat(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    if not can_use_ai(user):
        return (
            render_template(
                "partials/chat_pitch_analysis.html",
                analysis=None,
                startup=startup,
                error="Лимит AI-запросов исчерпан.",
            ),
            429,
        )
    upload = request.files.get("attach_file") or request.files.get("pitch_file")
    if not upload or not getattr(upload, "filename", ""):
        return (
            render_template(
                "partials/chat_pitch_analysis.html",
                analysis=None,
                startup=startup,
                error="Выбери документ, фото или видео.",
            ),
            422,
        )

    filename = (upload.filename or "")[:120]
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    mime = (upload.mimetype or "").lower()

    image_ext = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    video_ext = {".mp4", ".mov", ".webm", ".m4v", ".avi"}
    doc_ext = {".pptx", ".pdf", ".txt"}

    if ext in video_ext or mime.startswith("video/"):
        from ..services.video_attach import VideoAttachError, prepare_video_for_ai

        try:
            data = upload.read()
            _, attach_meta = _save_chat_bytes(startup, data, filename=filename, kind="video")
            packed = prepare_video_for_ai(data, filename)
            reply = describe_chat_video(
                user,
                startup,
                frames=packed.get("frames"),
                frames_b64=packed.get("frames_b64"),
                transcript=packed.get("transcript"),
                duration=packed.get("duration"),
                filename=filename,
                has_speech=bool(packed.get("has_speech")),
            )
            db.session.commit()
            consume_ai_request(user)
            track(
                "chat_video_attach",
                user,
                startup_id=startup_id,
                frames=packed.get("frame_count"),
                duration=packed.get("duration"),
            )
            _persist_chat_media(user, startup, attach=attach_meta, reply=reply)
        except VideoAttachError as exc:
            return (
                render_template(
                    "partials/chat_attach_note.html",
                    kind="video",
                    filename=filename,
                    message=str(exc),
                ),
                422,
            )
        except Exception:
            current_app.logger.exception("chat video attach failed")
            return (
                render_template(
                    "partials/chat_attach_note.html",
                    kind="video",
                    filename=filename,
                    message="AI временно не смог разобрать видео. Попробуй короче или пришли фото-кадры.",
                ),
                503,
            )
        return render_template(
            "partials/chat_attach_note.html",
            kind="video",
            filename=filename,
            message=reply,
            attach=attach_meta,
        )

    if ext in image_ext or mime.startswith("image/"):
        try:
            data = upload.read()
            _, attach_meta = _save_chat_bytes(startup, data, filename=filename, kind="image")
            reply = describe_chat_image(
                user,
                startup,
                data,
                mime=mime or "image/jpeg",
                filename=filename,
            )
            db.session.commit()
            consume_ai_request(user)
            track("chat_image_attach", user, startup_id=startup_id)
            _persist_chat_media(user, startup, attach=attach_meta, reply=reply)
        except ValueError as exc:
            return (
                render_template(
                    "partials/chat_attach_note.html",
                    kind="image",
                    filename=filename,
                    message=str(exc),
                ),
                422,
            )
        except Exception:
            current_app.logger.exception("chat image attach failed")
            return (
                render_template(
                    "partials/chat_attach_note.html",
                    kind="image",
                    filename=filename,
                    message="AI временно не смог прочитать фото.",
                ),
                503,
            )
        return render_template(
            "partials/chat_attach_note.html",
            kind="image",
            filename=filename,
            message=reply,
            attach=attach_meta,
        )

    if ext not in doc_ext:
        return (
            render_template(
                "partials/chat_attach_note.html",
                kind="file",
                filename=filename,
                message="Поддерживаю: фото, видео (.mp4/.mov/.webm), .pptx/.pdf/.txt.",
            ),
            422,
        )

    from ..services.pitch_deck import PitchDeckError, extract_from_upload

    previous = None
    if startup.pitch_analysis_json:
        try:
            previous = json.loads(startup.pitch_analysis_json)
        except json.JSONDecodeError:
            previous = None
    try:
        doc, attach_meta = _save_chat_document(startup, upload)
        slides = extract_from_upload(upload)
        analysis = analyze_pitch_deck(
            user,
            startup,
            slides,
            previous=previous if isinstance(previous, dict) else None,
            source="upload",
            filename=filename,
        )
        analysis["doc_id"] = doc.id
        analysis["attach"] = attach_meta
        startup.pitch_analysis_json = json.dumps(analysis, ensure_ascii=False)
        db.session.commit()
        consume_ai_request(user)
        track("pitch_analyze_chat", user, startup_id=startup_id, score=analysis.get("score"))
        from ..services.step_validation import maybe_complete_pitch_step

        step_msg = maybe_complete_pitch_step(user, startup, analysis)
        if step_msg:
            analysis["step_completed"] = step_msg
        _persist_chat_pitch(user, startup, filename, analysis, attach=attach_meta)
    except (PitchDeckError, ValueError) as exc:
        return (
            render_template(
                "partials/chat_pitch_analysis.html",
                analysis=None,
                startup=startup,
                filename=filename,
                error=str(exc),
            ),
            422,
        )
    except Exception:
        current_app.logger.exception("pitch analyze chat failed")
        return (
            render_template(
                "partials/chat_pitch_analysis.html",
                analysis=None,
                startup=startup,
                filename=filename,
                error="AI временно недоступен. Попробуй позже.",
            ),
            503,
        )
    return render_template(
        "partials/chat_pitch_analysis.html",
        analysis=analysis,
        startup=startup,
        filename=filename,
        attach=attach_meta,
    )


def _persist_chat_pitch(user, startup, filename: str, analysis: dict, *, attach: dict | None = None) -> None:
    """Save document + pitch card into the startup chat thread so it stays after reload."""
    try:
        from ..services.ai_threads import add_message, pitch_chat_intro

        thread = _thread_for_startup_chat(user, startup)
        if not thread:
            return
        attach_meta = attach or analysis.get("attach") or {
            "kind": "document",
            "filename": filename or analysis.get("filename") or "презентация",
        }
        add_message(
            thread,
            "user",
            attach_meta.get("filename") or filename or "презентация",
            meta={"attach": attach_meta},
        )
        score = int(analysis.get("score") or 0)
        compact = {
            "score": score,
            "verdict": "сильный" if score >= 66 else "нормальный" if score >= 46 else "слабый",
            "investor_ready": score >= 60,
            "summary": (analysis.get("summary") or "")[:500],
            "weaknesses": list(analysis.get("weaknesses") or [])[:3],
            "filename": analysis.get("filename") or filename,
            "delta": analysis.get("delta"),
            "doc_id": attach_meta.get("doc_id") or analysis.get("doc_id"),
        }
        add_message(
            thread,
            "assistant",
            pitch_chat_intro(startup, compact),
            meta={"pitch": compact},
        )
        if analysis.get("step_completed"):
            add_message(thread, "assistant", analysis["step_completed"])
    except Exception:
        current_app.logger.exception("persist chat pitch failed")


@bp.route("/startup/<int:startup_id>/finmodel", methods=["GET", "POST"])
def finmodel_page(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    form = FinModelForm(model_type=startup.business_model_type or "b2c")
    analysis = None
    if request.method == "POST" and form.validate_on_submit():
        if not can_use_ai(user):
            flash("Лимит AI исчерпан.", "error")
        else:
            inputs = {
                "CAC": form.cac.data or "",
                "ARPU": form.arpu.data or "",
                "Retention": form.retention.data or "",
                "LTV": form.ltv.data or "",
                "ACV": form.acv.data or "",
                "Sales cycle": form.sales_cycle.data or "",
                "Churn": form.churn.data or "",
                "Gross margin": form.margin.data or "",
                "Notes": form.notes.data or "",
            }
            try:
                analysis = analyze_fin_model(user, startup, form.model_type.data, inputs)
                payload = {"inputs": inputs, "analysis": analysis}
                startup.business_model_type = form.model_type.data
                startup.fin_model_json = json.dumps(payload, ensure_ascii=False)
                db.session.commit()
                consume_ai_request(user)
                track("finmodel", user, startup_id=startup_id, model=form.model_type.data)
            except Exception:
                current_app.logger.exception("finmodel failed")
                flash("AI временно недоступен.", "error")
    elif startup.fin_model_json:
        try:
            saved = json.loads(startup.fin_model_json)
            analysis = saved.get("analysis")
            if saved.get("inputs"):
                for key, val in saved["inputs"].items():
                    field_map = {
                        "CAC": "cac",
                        "ARPU": "arpu",
                        "Retention": "retention",
                        "LTV": "ltv",
                        "ACV": "acv",
                        "Sales cycle": "sales_cycle",
                        "Churn": "churn",
                        "Gross margin": "margin",
                        "Notes": "notes",
                    }
                    fname = field_map.get(key)
                    if fname and val:
                        getattr(form, fname).data = val
        except json.JSONDecodeError:
            analysis = None
    return render_template(
        "artifacts/finmodel.html",
        startup=startup,
        form=form,
        analysis=analysis,
        user=user,
        ai_remaining=ai_remaining(user),
    )


@bp.post("/startup/<int:startup_id>/poll")
def create_poll(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    form = IdeaPollForm()
    if not form.validate_on_submit():
        abort(422)
    try:
        poll = create_idea_poll(user, startup, form.hypothesis.data, form.title.data)
        track("idea_poll_created", user, startup_id=startup_id, poll_id=poll.id)
    except ValueError as exc:
        return render_template("partials/poll_error.html", error=str(exc)), 422
    item = feed_items_for([poll.activity], user)[0]
    return render_template("partials/poll_created.html", poll=poll, feed_url=url_for("main.feed", kind="poll"))


@bp.post("/feed/poll/<int:poll_id>/vote/<choice>")
def poll_vote(poll_id: int, choice: str):
    user = session_user()
    if not user:
        abort(401)
    from ..models.entities import IdeaPoll

    poll = db.session.get(IdeaPoll, poll_id) or abort(404)
    try:
        poll = cast_vote(poll, user, choice)
    except ValueError as exc:
        return render_template("partials/poll_error.html", error=str(exc)), 422
    activity = db.session.get(Activity, poll.activity_id) or abort(404)
    item = feed_items_for([activity], user)[0]
    return render_template("partials/activity_poll_block.html", feed_item=item)


@bp.post("/feed/poll/<int:poll_id>/refresh")
def poll_refresh(poll_id: int):
    user = session_user()
    if not user:
        abort(401)
    from ..models.entities import IdeaPoll

    poll = db.session.get(IdeaPoll, poll_id) or abort(404)
    poll = refresh_poll_score(poll)
    activity = db.session.get(Activity, poll.activity_id) or abort(404)
    item = feed_items_for([activity], user)[0]
    return render_template("partials/activity_poll_block.html", feed_item=item)


ALLOWED_DOC_EXT = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt"}
ALLOWED_DOC_KIND = {"pitch", "financials", "cap"}


def _documents_root() -> Path:
    folder = Path(current_app.config.get("DOCUMENTS_FOLDER", "uploads/documents"))
    if not folder.is_absolute():
        folder = Path(current_app.root_path).parent / folder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB".replace(".0 ", " ")
    return f"{n / (1024 * 1024):.1f} MB".replace(".0 ", " ")


def _save_chat_bytes(
    startup: Startup,
    data: bytes,
    *,
    filename: str,
    kind: str = "pitch",
) -> tuple[StartupDocument, dict]:
    """Persist chat attach bytes to disk + StartupDocument; return doc and attach meta."""
    from datetime import datetime, timezone

    raw_name = (filename or "file")[:120]
    safe = secure_filename(raw_name) or f"file{Path(raw_name).suffix.lower() or '.bin'}"
    ext = Path(safe).suffix.lower()
    if not data:
        raise ValueError("Файл пустой.")
    folder = _documents_root() / "chat" / str(startup.id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = int(datetime.now(timezone.utc).timestamp())
    path = folder / f"{stamp}_{safe}"
    path.write_bytes(data)
    doc_kind = kind if kind in ALLOWED_DOC_KIND | {"image", "video", "chat"} else "pitch"
    # StartupDocument.kind is free string — allow image/video
    doc = StartupDocument(
        startup_id=startup.id,
        kind=doc_kind,
        filename=safe,
        filepath=str(path),
    )
    db.session.add(doc)
    db.session.flush()
    attach_kind = "image" if kind == "image" else "video" if kind == "video" else "document"
    attach = {
        "kind": attach_kind,
        "filename": raw_name or safe,
        "ext": ext.lstrip(".").upper(),
        "size": len(data),
        "size_label": _format_bytes(len(data)),
        "doc_id": doc.id,
        "download_url": url_for("extensions.download_document", startup_id=startup.id, doc_id=doc.id),
    }
    return doc, attach


def _save_chat_document(startup: Startup, upload) -> tuple[StartupDocument, dict]:
    raw_name = (upload.filename or "file")[:120]
    data = upload.read()
    try:
        upload.stream.seek(0)
    except Exception:
        pass
    return _save_chat_bytes(startup, data, filename=raw_name, kind="pitch")


def _thread_for_startup_chat(user, startup):
    from ..models.entities import AiThread
    from ..services.ai_threads import resolve_thread

    thread = resolve_thread(user, session.get("ai_thread_id"))
    if not thread or (thread.startup_id and thread.startup_id != startup.id):
        thread = (
            AiThread.query.filter_by(user_id=user.id, startup_id=startup.id)
            .order_by(AiThread.updated_at.desc())
            .first()
        )
    return thread


def _persist_chat_media(user, startup, *, attach: dict, reply: str) -> None:
    try:
        from ..services.ai_threads import add_message

        thread = _thread_for_startup_chat(user, startup)
        if not thread:
            return
        add_message(
            thread,
            "user",
            attach.get("filename") or "файл",
            meta={"attach": attach},
        )
        add_message(thread, "assistant", reply)
    except Exception:
        current_app.logger.exception("persist chat media failed")


@bp.post("/startup/<int:startup_id>/documents")
def upload_document(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    upload = request.files.get("document")
    if not upload or not upload.filename:
        abort(422)
    filename = secure_filename(upload.filename)
    ext = Path(filename).suffix.lower()
    if not filename or ext not in ALLOWED_DOC_EXT:
        abort(422)
    kind = request.form.get("kind", "pitch")
    if kind not in ALLOWED_DOC_KIND:
        kind = "pitch"
    folder = _documents_root()
    path = folder / f"{startup_id}_{filename}"
    upload.save(path)
    doc = StartupDocument(
        startup_id=startup.id,
        kind=kind,
        filename=filename,
        filepath=str(path),
    )
    db.session.add(doc)
    db.session.commit()
    return redirect(url_for("main.startup_detail", startup_id=startup.id))


@bp.get("/startup/<int:startup_id>/documents/<int:doc_id>")
def download_document(startup_id: int, doc_id: int):
    user = session_user()
    if not user:
        abort(401)
    startup = db.session.get(Startup, startup_id) or abort(404)
    doc = StartupDocument.query.filter_by(id=doc_id, startup_id=startup.id).first_or_404()
    is_owner = startup.owner_id == user.id
    if not is_owner and not (is_investor(user) and user.is_verified_investor):
        abort(403)
    path = Path(doc.filepath)
    from ..security import send_contained_file

    return send_contained_file(_documents_root(), path, doc.filename)


@bp.post("/investor/candidates/<int:startup_id>/deal")
def investor_deal_update(startup_id: int):
    user = session_user()
    if not user or not is_investor(user):
        abort(403)
    startup = db.session.get(Startup, startup_id) or abort(404)
    form = DealForm()
    if not form.validate_on_submit():
        abort(422)
    deal = set_deal_status(user, startup, form.status.data, form.notes.data)
    return render_template(
        "partials/investor_deal_form.html",
        startup=startup,
        deal=deal,
        form=form,
    )


@bp.post("/feed/<int:activity_id>/react/<reaction>")
def feed_react(activity_id: int, reaction: str):
    user = session_user()
    if not user:
        abort(401)
    from ..models.entities import Activity

    activity = db.session.get(Activity, activity_id) or abort(404)
    if reaction not in {"fire", "idea", "ship"}:
        abort(400)
    existing = ActivityReaction.query.filter_by(
        activity_id=activity.id, user_id=user.id, reaction=reaction
    ).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(ActivityReaction(activity_id=activity.id, user_id=user.id, reaction=reaction))
    db.session.commit()
    from ..services.idea_poll import poll_for_activity, refresh_poll_score

    poll = poll_for_activity(activity.id)
    if poll:
        refresh_poll_score(poll)
    item = feed_items_for([activity], user)[0]
    return render_template("partials/activity_reactions.html", feed_item=item)


@bp.post("/locale")
def set_locale():
    from ..routes.main import profile_set_locale

    return profile_set_locale()


@bp.post("/startup/<int:startup_id>/switch")
def switch_startup(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    user.active_startup_id = startup.id
    db.session.commit()
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Redirect": url_for("main.home")}
    return redirect(url_for("main.home"))


@bp.post("/admin/tasks/retention")
@bp.get("/admin/tasks/retention")
def admin_run_retention():
    from flask import current_app, jsonify

    from ..routes.admin import admin_logged_in
    from ..services.tasks import run_poll_validation_expiry, run_retention_push_campaign, run_weekly_goal_reminders

    from ..security import tokens_match

    token = (request.headers.get("X-Task-Token") or "").strip()
    expected = current_app.config.get("TASK_TOKEN") or ""
    token_ok = tokens_match(expected, token)
    if not admin_logged_in() and not token_ok:
        abort(403)
    r1 = run_retention_push_campaign()
    r2 = run_weekly_goal_reminders()
    r3 = run_poll_validation_expiry()
    return jsonify({"ok": True, "retention": r1, "goals": r2, "poll_expiry": r3})
