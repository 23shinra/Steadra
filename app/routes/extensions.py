import json
import os
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, session, url_for
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from ..access import is_investor
from ..models import db
from ..models.entities import Activity, ActivityReaction, Startup, StartupDocument, User
from ..routes.auth import session_user
from ..services.ai_agent import (
    analyze_fin_model,
    analyze_pitch_text,
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
    pitch_text = TextAreaField("Текст питча", validators=[DataRequired(), Length(min=50, max=6000)])


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
        active_tab="home",
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
        active_tab="profile",
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
        active_tab="profile",
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
        active_tab="home",
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
    if request.method == "POST" and form.validate_on_submit():
        if not can_use_ai(user):
            flash("Лимит AI исчерпан.", "error")
        else:
            try:
                analysis = analyze_pitch_text(user, startup, form.pitch_text.data)
                startup.pitch_analysis_json = json.dumps(analysis, ensure_ascii=False)
                db.session.commit()
                consume_ai_request(user)
                track("pitch_analyze", user, startup_id=startup_id, score=analysis.get("score"))
            except Exception:
                current_app.logger.exception("pitch analyze failed")
                flash("AI временно недоступен.", "error")
    elif startup.pitch_analysis_json:
        try:
            analysis = json.loads(startup.pitch_analysis_json)
        except json.JSONDecodeError:
            analysis = None
    return render_template(
        "artifacts/pitch_analyze.html",
        startup=startup,
        form=form,
        analysis=analysis,
        user=user,
        ai_remaining=ai_remaining(user),
    )


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


@bp.post("/startup/<int:startup_id>/documents")
def upload_document(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    upload = request.files.get("document")
    if not upload or not upload.filename:
        abort(422)
    kind = request.form.get("kind", "pitch")
    folder = Path(current_app.config.get("DOCUMENTS_FOLDER", "uploads/documents"))
    folder.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(upload.filename)
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
    user = session_user()
    locale = request.form.get("locale", "ru")
    if locale not in current_app.config.get("BABEL_SUPPORTED_LOCALES", ["ru"]):
        locale = "ru"
    session["locale"] = locale
    if user:
        user.locale = locale
        db.session.commit()
    return redirect(request.referrer or url_for("main.home"))


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
def admin_run_retention():
    from ..routes.admin import admin_logged_in
    from ..services.tasks import run_retention_push_campaign, run_weekly_goal_reminders

    if not admin_logged_in():
        abort(403)
    r1 = run_retention_push_campaign()
    r2 = run_weekly_goal_reminders()
    return {"ok": True, "retention": r1, "goals": r2}
