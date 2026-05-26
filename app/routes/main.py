from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_wtf import FlaskForm
from wtforms import BooleanField, HiddenField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from ..models import db
from ..models.entities import Activity, ActivityComment, ActivityLike, AiMessage, AiThread, RoadmapStepLog, Startup, StepValidationRequest, TeamInvitation, User
from ..access import ACCOUNT_INVESTOR, is_investor
from ..roles import ROLES, founder_roles, is_valid_role_id, role_id_for_user, role_label_for_id, INVESTOR_ROLE_LABEL
from ..services.ai_agent import (
    generate_context_turn,
    generate_roadmap_completed_turn,
    generate_roadmap_smart_turn,
    generate_roadmap_steps,
    generate_roast,
)
from ..services.ai_threads import add_message, create_thread, history_for_thread, resolve_thread, threads_for_user, update_thread_summary
from ..services.openai_chat import generate_thread_summary
from ..services.roadmap import (
    advance_roadmap,
    branch_map_state,
    dump_steps,
    is_finished,
    needs_roadmap_rebuild,
    progress_stats,
    step_at,
    step_logs_by_index,
    steps_for_startup,
)
from ..services.founder_mission import mission_for_user
from ..services.onboarding_checklist import onboarding_checklist as build_onboarding_checklist
from ..services.notifications import list_for as notifications_for, mark_all_read, mark_read, run_retention_checks, unread_count
from ..services.push import save_subscription
from ..services.step_goals import ensure_weekly_goals, toggle_goal, weekly_goals_summary
from ..services.feed_social import feed_items_for, startup_for_feed_post
from ..services.team import (
    accept_invite,
    decline_invite,
    invite_state,
    primary_startup,
    profile_team_context,
    send_invite,
    startup_team_profile,
)
from ..utils.avatars import delete_avatar_files, find_avatar_file, save_avatar_file

bp = Blueprint("main", __name__)

_ONBOARDING_SKIP = {
    "main.service_worker",
    "main.serve_avatar",
    "main.onboarding",
}

_PUBLIC_ENDPOINTS = {
    "main.onboarding",
    "main.service_worker",
    "main.serve_avatar",
}

_INVESTOR_ALLOWED = {
    "main.profile",
    "main.profile_edit",
    "main.profile_edit_submit",
    "main.user_profile",
    "main.leaderboard",
    "main.serve_avatar",
    "main.service_worker",
}


@bp.before_request
def require_login():
    if not request.endpoint:
        return None
    if request.endpoint.startswith("auth."):
        return None
    if request.endpoint.startswith("admin."):
        return None
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if request.endpoint.startswith("static."):
        return None
    if not session_user():
        return redirect(url_for("auth.login"))
    return None


@bp.before_request
def require_profile_onboarding():
    if not request.endpoint or request.endpoint.startswith("auth."):
        return None
    if request.endpoint.startswith("investor."):
        return None
    if request.endpoint in _ONBOARDING_SKIP:
        return None
    user = session_user()
    if user and not user.onboarding_done:
        return redirect(url_for("auth.profile_onboarding"))
    from ..access import is_investor

    if user and is_investor(user) and request.endpoint not in _INVESTOR_ALLOWED:
        return redirect(url_for("investor.candidates"))
    return None


@bp.get("/uploads/avatars/<int:user_id>")
def serve_avatar(user_id: int):
    avatar_file = find_avatar_file(user_id)
    if not avatar_file:
        abort(404)
    return send_from_directory(avatar_file.parent, avatar_file.name)


@bp.get("/service-worker.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "js/service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


def current_user():
    return session_user()


def session_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def user_startups(user: User | None):
    if not user:
        return []
    return Startup.query.filter_by(owner_id=user.id).order_by(Startup.health.desc()).all()


def active_startup_for(user: User | None):
    if not user:
        return None
    if user.active_startup_id:
        startup = db.session.get(Startup, user.active_startup_id)
        if startup and startup.owner_id == user.id:
            return startup
    startups = user_startups(user)
    return startups[0] if startups else None


def progress_startup_for(user: User | None, active_thread: AiThread | None = None) -> Startup | None:
    if not user:
        return None
    if active_thread and active_thread.startup_id:
        startup = db.session.get(Startup, active_thread.startup_id)
        if startup and startup.owner_id == user.id:
            return startup
    return Startup.query.filter_by(owner_id=user.id).order_by(Startup.id.desc()).first()


def _require_chat_startup_thread(user: User, startup: Startup) -> tuple[AiThread | None, str | None]:
    if not request.headers.get("HX-Request"):
        return None, "Отправляй заявку только из AI-чата."
    thread_id = request.form.get("thread_id", type=int)
    if not thread_id:
        return None, "Открой чат проекта и отправь заявку оттуда."
    thread = resolve_thread(user, thread_id)
    if not thread or thread.startup_id != startup.id:
        return None, "Заявка должна быть отправлена из чата этого проекта."
    return thread, None


def _chat_step_context(user: User, progress_startup: Startup | None, active_thread: AiThread | None) -> dict:
    from ..models.entities import StepValidationRequest
    from ..services.roadmap import is_finished, step_at
    from ..services.step_validation import pending_for_startup

    pending_validation = None
    last_validation = None
    show_step_submit = False
    current_step = None
    if not progress_startup or not active_thread or active_thread.startup_id != progress_startup.id:
        return {
            "pending_validation": pending_validation,
            "last_validation": last_validation,
            "show_step_submit": show_step_submit,
            "current_step": current_step,
        }
    steps = steps_for_startup(progress_startup)
    if is_finished(progress_startup.roadmap_step, steps):
        return {
            "pending_validation": pending_validation,
            "last_validation": last_validation,
            "show_step_submit": show_step_submit,
            "current_step": current_step,
        }
    current_step = step_at(progress_startup.roadmap_step, steps)
    pending_validation = pending_for_startup(progress_startup.id, progress_startup.roadmap_step)
    last_validation = (
        StepValidationRequest.query.filter_by(
            startup_id=progress_startup.id,
            step_index=progress_startup.roadmap_step,
        )
        .order_by(StepValidationRequest.created_at.desc())
        .first()
    )
    if not pending_validation or pending_validation.status in (
        StepValidationRequest.STATUS_AI_REJECTED,
        StepValidationRequest.STATUS_ADMIN_REJECTED,
    ):
        show_step_submit = True
    return {
        "pending_validation": pending_validation,
        "last_validation": last_validation,
        "show_step_submit": show_step_submit,
        "current_step": current_step,
    }


def dashboard_data():
    user = current_user()
    startups = Startup.query.order_by(Startup.health.desc()).all()
    activities = Activity.query.order_by(Activity.created_at.desc(), Activity.id.desc()).limit(8).all()
    leaders = (
        User.query.filter(User.account_type != ACCOUNT_INVESTOR)
        .order_by(User.score.desc(), User.id.asc())
        .all()
    )
    active_startup = active_startup_for(user)
    feed_items = feed_items_for(activities, session_user())
    return user, startups, activities, feed_items, leaders, active_startup


class ChatForm(FlaskForm):
    message = TextAreaField("Сообщение", validators=[DataRequired(), Length(min=2, max=900)])
    thread_id = HiddenField(validators=[Optional()])


class FeedPostForm(FlaskForm):
    body = TextAreaField("Пост", validators=[DataRequired(), Length(min=2, max=900)])
    title = StringField("Заголовок", validators=[Optional(), Length(max=160)])
    kind = SelectField(
        "Тип",
        choices=[
            ("post", "Апдейт"),
            ("question", "Вопрос"),
            ("hiring", "Найм"),
            ("cofounder", "Ищу co-founder"),
        ],
        default="post",
    )


class StepCompleteForm(FlaskForm):
    report = TextAreaField("Отчёт", validators=[DataRequired(), Length(min=20, max=500)])
    evidence_url = StringField("Ссылка-доказательство", validators=[Optional(), Length(max=500)])


class TooSubmitForm(FlaskForm):
    company_name = StringField("Название ТОО", validators=[DataRequired(), Length(min=2, max=160)])
    bin = StringField("BIN", validators=[DataRequired(), Length(min=12, max=12)])
    message = TextAreaField("Сообщение", validators=[DataRequired(), Length(min=10, max=900)])
    evidence_url = StringField("Ссылка на выписку", validators=[Optional(), Length(max=500)])


class FeedCommentForm(FlaskForm):
    body = StringField("Комментарий", validators=[DataRequired(), Length(min=1, max=500)])


class ProfileForm(FlaskForm):
    role = StringField("Роль", validators=[DataRequired()])
    name = StringField("Имя", validators=[DataRequired(), Length(min=2, max=80)])
    remove_avatar = BooleanField("Удалить фото")

    def validate_role(self, field):
        if not is_valid_role_id(field.data):
            raise ValidationError("Выбери роль из списка.")


@bp.get("/")
def onboarding():
    user = session_user()
    if user:
        if not user.onboarding_done:
            return redirect(url_for("auth.profile_onboarding"))
        return home()
    return render_template("onboarding.html", hide_nav=True)


@bp.get("/app")
def home():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    _, startups, activities, feed_items, leaders, active_startup = dashboard_data()
    mission = None
    onboarding = None
    if user and not is_investor(user):
        run_retention_checks(user)
        mission = mission_for_user(user)
        onboarding = build_onboarding_checklist(user)
    return render_template(
        "home.html",
        user=user,
        startups=startups,
        activities=activities,
        feed_items=feed_items,
        leaders=leaders,
        active_startup=active_startup,
        user_startups=user_startups(user) if user else [],
        active_tab="home",
        mission=mission,
        onboarding=onboarding,
        unread_notif_count=unread_count(session_user()),
        vapid_public_key=current_app.config.get("VAPID_PUBLIC_KEY", ""),
    )


@bp.get("/feed")
def feed():
    user = session_user()
    kind = request.args.get("kind", "all")
    q = Activity.query
    if kind and kind != "all":
        q = q.filter_by(kind=kind)
    activities = q.order_by(Activity.created_at.desc(), Activity.id.desc()).limit(40).all()
    feed_items = feed_items_for(activities, user)
    return render_template(
        "feed.html",
        user=user,
        feed_items=feed_items,
        post_form=FeedPostForm(),
        active_tab="feed",
        filter_kind=kind,
    )


@bp.post("/feed/post")
def feed_post():
    user = session_user()
    if not user:
        return render_template("partials/feed_error.html", error="Войди, чтобы публиковать."), 401
    form = FeedPostForm()
    if not form.validate_on_submit():
        return render_template("partials/feed_error.html", error="Напиши текст поста."), 422
    body = form.body.data.strip()
    title = (form.title.data or "").strip() or body[:80]
    post_kind = form.kind.data or "post"
    startup = startup_for_feed_post(user)
    activity = Activity(
        kind=post_kind,
        title=title[:160],
        body=body,
        impact=0,
        user_id=user.id,
        startup_id=startup.id if startup else None,
    )
    db.session.add(activity)
    db.session.commit()
    from ..services.achievements import check_and_grant
    from ..services.analytics import track

    check_and_grant(user, event="post", startup=startup)
    track("feed_post", user, kind=post_kind)
    item = feed_items_for([activity], user)[0]
    return render_template("partials/activity_card.html", feed_item=item, show_social=True)


@bp.post("/feed/<int:activity_id>/like")
def feed_like(activity_id: int):
    user = session_user()
    if not user:
        return render_template("partials/feed_error.html", error="Войди, чтобы ставить лайки."), 401
    activity = db.session.get(Activity, activity_id) or abort(404)
    existing = ActivityLike.query.filter_by(activity_id=activity.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(ActivityLike(activity_id=activity.id, user_id=user.id))
    db.session.commit()
    item = feed_items_for([activity], user)[0]
    return render_template("partials/activity_like_button.html", feed_item=item)


@bp.post("/feed/<int:activity_id>/comment")
def feed_comment(activity_id: int):
    user = session_user()
    if not user:
        return render_template("partials/feed_error.html", error="Войди, чтобы комментировать."), 401
    activity = db.session.get(Activity, activity_id) or abort(404)
    form = FeedCommentForm()
    if not form.validate_on_submit():
        return render_template("partials/feed_error.html", error="Напиши комментарий."), 422
    comment = ActivityComment(
        activity_id=activity.id,
        user_id=user.id,
        body=form.body.data.strip(),
    )
    db.session.add(comment)
    db.session.commit()
    item = feed_items_for([activity], user)[0]
    return render_template("partials/activity_comments.html", feed_item=item)


@bp.post("/team/invite/<int:user_id>")
def team_invite(user_id: int):
    user = session_user()
    if not user:
        return render_template("partials/feed_error.html", error="Войди, чтобы приглашать."), 401
    if is_investor(user):
        return render_template("partials/feed_error.html", error="Инвесторам недоступно."), 403
    invitee = db.session.get(User, user_id) or abort(404)
    invite, error = send_invite(user, invitee.id)
    if error:
        return render_template("partials/feed_error.html", error=error), 422
    startup = primary_startup(user)
    status = invite_state(user, invitee, startup)
    activity_id = request.form.get("activity_id", "")
    return render_template(
        "partials/team_invite_button.html",
        invitee=invitee,
        invite_status=status,
        activity_id=activity_id,
        invite_startup=startup,
    )


@bp.get("/team/invites/<int:invite_id>")
def team_invite_detail(invite_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    invite = db.session.get(TeamInvitation, invite_id) or abort(404)
    if invite.invitee_id != user.id:
        abort(403)
    if invite.status != TeamInvitation.STATUS_PENDING:
        flash("Приглашение уже обработано.", "info")
        return redirect(url_for("main.profile"))
    profile = startup_team_profile(invite.startup)
    return render_template(
        "team/invite_detail.html",
        invite=invite,
        startup=profile["startup"],
        inviter=invite.inviter,
        progress=profile["progress"],
        map_nodes=profile["map_nodes"],
        current_step=profile["current_step"],
        days_on_step=profile["days_on_step"],
        weekly_goals=profile["weekly_goals"],
        team=profile["team"],
        step_timeline=profile["step_timeline"],
        finished=profile["finished"],
        user=user,
        active_tab="profile",
    )


@bp.post("/team/invites/<int:invite_id>/accept")
def team_invite_accept(invite_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    invite = db.session.get(TeamInvitation, invite_id) or abort(404)
    _, error = accept_invite(invite, user)
    if error:
        flash(error, "error")
    else:
        flash(f"Вы в команде «{invite.startup.name}».", "success")
    return redirect(url_for("main.profile"))


@bp.post("/team/invites/<int:invite_id>/decline")
def team_invite_decline(invite_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    invite = db.session.get(TeamInvitation, invite_id) or abort(404)
    error = decline_invite(invite, user)
    if error:
        flash(error, "error")
    else:
        flash("Приглашение отклонено.", "info")
    return redirect(url_for("main.profile"))


@bp.get("/leaderboard")
def leaderboard():
    user = session_user()
    region = request.args.get("region", "")
    q = User.query.filter(User.account_type != ACCOUNT_INVESTOR)
    if region:
        q = q.filter_by(region=region)
    leaders = q.order_by(User.score.desc(), User.id.asc()).all()
    return render_template(
        "leaderboard.html",
        user=user,
        top_leaders=leaders[:3],
        rest_leaders=leaders[3:],
        active_tab="leaderboard",
        filter_region=region,
    )


def _thread_id_from_form(form: ChatForm) -> int | None:
    raw = (form.thread_id.data or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@bp.get("/ai")
def ai():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    from ..services.ai_limits import ai_remaining

    thread_id = request.args.get("thread", type=int)
    active_thread = resolve_thread(user, thread_id) if thread_id else None
    form = ChatForm()
    if active_thread:
        form.thread_id.data = str(active_thread.id)
    messages = active_thread.messages if active_thread else []
    show_intro = not messages
    onboarding_mode = request.args.get("onboarding") == "1" and show_intro
    progress_startup = progress_startup_for(user, active_thread)
    map_steps = steps_for_startup(progress_startup) if progress_startup else []
    from ..services.too_validation import can_submit_too, pending_too_for_startup

    too_pending = pending_too_for_startup(progress_startup.id) if progress_startup else None
    show_too_submit = bool(progress_startup and can_submit_too(progress_startup))
    step_ctx = _chat_step_context(user, progress_startup, active_thread)
    return render_template(
        "ai.html",
        form=form,
        active_tab="ai",
        is_chat=True,
        threads=threads_for_user(user),
        active_thread=active_thread,
        messages=messages,
        show_intro=show_intro,
        onboarding_mode=onboarding_mode,
        progress_startup=progress_startup,
        map_steps=map_steps,
        ai_remaining=ai_remaining(user),
        show_too_submit=show_too_submit,
        too_pending=too_pending,
        too_form=TooSubmitForm(),
        complete_form=StepCompleteForm(),
        **step_ctx,
    )


def _regenerate_roadmap_for_startup(user: User, startup: Startup) -> list:
    thread = (
        AiThread.query.filter_by(startup_id=startup.id, user_id=user.id)
        .order_by(AiThread.id.desc())
        .first()
    )
    history = history_for_thread(thread) if thread else []
    plan = generate_roadmap_steps(history, user, startup.name, startup.tagline)
    return plan.get("steps") or steps_for_startup(None)


def _apply_roadmap_rebuild(user: User, startup: Startup) -> list:
    steps = _regenerate_roadmap_for_startup(user, startup)
    startup.roadmap_steps_json = dump_steps(steps)
    startup.roadmap_step = 0
    startup.stage = steps[0]["label"]
    startup.roadmap_started_at = datetime.now(timezone.utc)
    RoadmapStepLog.query.filter_by(startup_id=startup.id).delete()
    db.session.add(startup)
    db.session.commit()
    return steps


@bp.get("/progress")
def progress_page():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    if not is_investor(user):
        run_retention_checks(user)
    startup_id = request.args.get("startup", type=int)
    if startup_id:
        startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    else:
        startup = progress_startup_for(user)
    roadmap_rebuilt = False
    if startup and needs_roadmap_rebuild(startup):
        try:
            _apply_roadmap_rebuild(user, startup)
            roadmap_rebuilt = True
        except Exception:
            current_app.logger.exception("auto roadmap rebuild failed")
    steps = steps_for_startup(startup) if startup else []
    progress = progress_stats(startup.roadmap_step, steps) if startup else None
    map_nodes = branch_map_state(startup.roadmap_step, steps, step_logs_by_index(startup)) if startup else []
    thread = None
    if startup:
        thread = AiThread.query.filter_by(startup_id=startup.id, user_id=user.id).order_by(AiThread.id.desc()).first()
        ensure_weekly_goals(startup)
    current_step = None if not startup or progress["finished"] else step_at(startup.roadmap_step, steps)
    days_on_step = None
    weekly_goals = weekly_goals_summary(startup) if startup else None
    if startup and current_step:
        from ..services.roadmap import days_on_current_step

        days_on_step = days_on_current_step(startup, steps)
    complete_form = StepCompleteForm()
    from ..services.partners import partners_for_step

    step_key = current_step.get("key") if current_step else None
    if current_step and not step_key:
        from ..services.step_prompts import infer_step_key as _infer

        step_key = _infer(current_step)
    partners = partners_for_step(step_key, getattr(user, "region", None)) if current_step else []
    user_startups_list = user_startups(user)
    pending_validation = None
    last_validation = None
    if startup and current_step:
        from ..services.step_validation import pending_for_startup
        from ..models.entities import StepValidationRequest

        pending_validation = pending_for_startup(startup.id, startup.roadmap_step)
        last_validation = (
            StepValidationRequest.query.filter_by(startup_id=startup.id, step_index=startup.roadmap_step)
            .order_by(StepValidationRequest.created_at.desc())
            .first()
        )
    import json
    from ..services.idea_poll import poll_for_startup

    startup_poll = poll_for_startup(startup.id) if startup else None
    pitch_analysis = None
    fin_model = None
    if startup and startup.pitch_analysis_json:
        try:
            pitch_analysis = json.loads(startup.pitch_analysis_json)
        except json.JSONDecodeError:
            pitch_analysis = None
    if startup and startup.fin_model_json:
        try:
            fin_model = json.loads(startup.fin_model_json)
        except json.JSONDecodeError:
            fin_model = None
    from ..routes.extensions import FinModelForm, IdeaPollForm, PitchAnalyzeForm

    from ..services.too_validation import can_submit_too, pending_too_for_startup

    too_pending = pending_too_for_startup(startup.id) if startup else None
    return render_template(
        "progress.html",
        active_tab="progress",
        progress_startup=startup,
        map_nodes=map_nodes,
        progress=progress,
        thread=thread,
        roadmap_rebuilt=roadmap_rebuilt,
        can_rebuild_map=bool(startup),
        current_step=current_step,
        step_key=step_key,
        days_on_step=days_on_step,
        weekly_goals=weekly_goals,
        complete_form=complete_form,
        partners=partners,
        user_startups=user_startups_list,
        pending_validation=pending_validation,
        last_validation=last_validation,
        startup_poll=startup_poll,
        pitch_analysis=pitch_analysis,
        fin_model=fin_model,
        poll_form=IdeaPollForm(),
        pitch_form=PitchAnalyzeForm(),
        finmodel_form=FinModelForm(model_type=(startup.business_model_type if startup else None) or "b2c"),
        show_too_submit=bool(startup and can_submit_too(startup)),
        too_pending=too_pending,
        too_form=TooSubmitForm(),
    )


@bp.post("/progress/rebuild")
def progress_rebuild():
    user = session_user() or current_user()
    startup_id = request.form.get("startup_id", type=int) or request.args.get("startup", type=int)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    try:
        _apply_roadmap_rebuild(user, startup)
    except Exception:
        current_app.logger.exception("manual roadmap rebuild failed")
        flash("Не удалось перестроить карту. Попробуй позже.", "error")
        return redirect(url_for("main.progress_page", startup=startup.id))
    flash(f"Карта обновлена: {len(steps_for_startup(startup))} шагов.", "success")
    return redirect(url_for("main.progress_page", startup=startup.id))


@bp.post("/progress/<int:startup_id>/complete")
def progress_complete(startup_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    flash("Отчёт на проверку отправляется только из AI-чата.", "error")
    thread = AiThread.query.filter_by(startup_id=startup.id, user_id=user.id).order_by(AiThread.id.desc()).first()
    if thread:
        return redirect(url_for("main.ai", thread=thread.id))
    return redirect(url_for("main.ai"))


@bp.post("/startup/<int:startup_id>/step/submit")
def step_submit(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    if is_investor(user):
        abort(403)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    _, chat_error = _require_chat_startup_thread(user, startup)
    if chat_error:
        return render_template("partials/step_submit_error.html", error=chat_error), 422

    form = StepCompleteForm()
    if not form.validate_on_submit():
        step_ctx = _chat_step_context(user, startup, resolve_thread(user, request.form.get("thread_id", type=int)))
        return (
            render_template(
                "partials/chat_step_submit.html",
                progress_startup=startup,
                active_thread=resolve_thread(user, request.form.get("thread_id", type=int)),
                complete_form=form,
                submit_error="Напиши отчёт от 20 до 500 символов.",
                **step_ctx,
            ),
            422,
        )

    from ..services.ai_limits import can_use_ai, consume_ai_request
    from ..services.step_validation import submit_step_validation

    if not can_use_ai(user):
        return render_template("partials/step_submit_error.html", error="Лимит AI-запросов исчерпан."), 429

    req, message = submit_step_validation(
        user,
        startup,
        report=form.report.data.strip(),
        evidence_url=(form.evidence_url.data or "").strip() or None,
        evidence_file=request.files.get("evidence_file"),
    )
    consume_ai_request(user)
    if req and req.status in (
        StepValidationRequest.STATUS_PENDING_ADMIN,
        StepValidationRequest.STATUS_PENDING_AI,
    ):
        return render_template("partials/step_submit_success.html", message=message)
    return render_template("partials/step_submit_error.html", error=message), 422


@bp.post("/startup/<int:startup_id>/too/submit")
def too_submit(startup_id: int):
    user = session_user()
    if not user:
        abort(401)
    if is_investor(user):
        abort(403)
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    _, chat_error = _require_chat_startup_thread(user, startup)
    if chat_error:
        if request.headers.get("HX-Request"):
            return render_template("partials/too_submit_error.html", error=chat_error), 422
        flash(chat_error, "error")
        thread = resolve_thread(user, request.form.get("thread_id", type=int))
        if thread:
            return redirect(url_for("main.ai", thread=thread.id))
        return redirect(url_for("main.ai"))

    form = TooSubmitForm()
    if not form.validate_on_submit():
        if request.headers.get("HX-Request"):
            return render_template("partials/too_submit_error.html", error="Заполни все поля корректно."), 422
        flash("Заполни все поля заявки на ТОО.", "error")
        thread = resolve_thread(user, request.form.get("thread_id", type=int))
        if thread:
            return redirect(url_for("main.ai", thread=thread.id))
        return redirect(url_for("main.ai"))

    from ..services.too_validation import submit_too_validation

    req, message = submit_too_validation(
        user,
        startup,
        company_name=form.company_name.data,
        bin_number=form.bin.data,
        message=form.message.data,
        evidence_url=form.evidence_url.data,
        evidence_file=request.files.get("evidence_file"),
    )
    is_ok = req is not None
    if request.headers.get("HX-Request"):
        if is_ok:
            return render_template("partials/too_submit_success.html", message=message)
        return render_template("partials/too_submit_error.html", error=message), 422
    flash(message, "success" if is_ok else "error")
    thread = resolve_thread(user, request.form.get("thread_id", type=int))
    if thread:
        return redirect(url_for("main.ai", thread=thread.id))
    return redirect(url_for("main.ai"))


@bp.post("/progress/goals/<int:goal_id>/toggle")
def progress_goal_toggle(goal_id: int):
    user = session_user()
    if not user:
        return render_template("partials/feed_error.html", error="Войди в аккаунт."), 401
    startup_id = request.form.get("startup_id", type=int)
    if not startup_id:
        return render_template("partials/feed_error.html", error="Проект не найден."), 422
    startup = Startup.query.filter_by(id=startup_id, owner_id=user.id).first_or_404()
    goal = toggle_goal(goal_id, startup.id)
    if not goal:
        abort(404)
    weekly_goals = weekly_goals_summary(startup)
    return render_template(
        "partials/step_goals.html",
        weekly_goals=weekly_goals,
        progress_startup=startup,
    )


@bp.get("/notifications")
def notifications_page():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    items = notifications_for(user)
    return render_template(
        "notifications.html",
        user=user,
        notifications=items,
        active_tab="home",
        unread_notif_count=0,
    )


@bp.post("/notifications/<int:notification_id>/read")
def notification_read(notification_id: int):
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    mark_read(notification_id, user.id)
    if request.headers.get("HX-Request"):
        return "", 204
    return redirect(url_for("main.notifications_page"))


@bp.post("/notifications/read-all")
def notifications_read_all():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    mark_all_read(user)
    return redirect(url_for("main.notifications_page"))


@bp.post("/push/subscribe")
def push_subscribe():
    user = session_user()
    if not user:
        return jsonify({"ok": False, "error": "auth"}), 401
    payload = request.get_json(silent=True) or {}
    sub = save_subscription(user, payload)
    if not sub:
        return jsonify({"ok": False, "error": "invalid"}), 422
    return jsonify({"ok": True})


@bp.get("/ai/new")
def ai_new():
    return redirect(url_for("main.ai"))


def _rollback_last_user_message(thread: AiThread, message: str) -> None:
    last = (
        AiMessage.query.filter_by(thread_id=thread.id, role="user")
        .order_by(AiMessage.id.desc())
        .first()
    )
    if last and last.content == message:
        db.session.delete(last)
        db.session.commit()


@bp.post("/ai/validate")
def ai_validate():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    thread_id = request.form.get("thread_id", type=int)
    thread = resolve_thread(user, thread_id)
    if not thread or thread.phase != "roast":
        return render_template("partials/chat_error.html", error="Сначала опиши идею для прожарки."), 422

    name = (thread.idea_name or "Новый проект").strip()[:100]
    tagline = (thread.idea_tagline or "Стартап из AI-чата").strip()[:180]
    history = history_for_thread(thread)
    plan_summary = ""
    try:
        plan = generate_roadmap_steps(history, user, name, tagline)
        steps = plan.get("steps") or steps_for_startup(None)
        plan_summary = (plan.get("summary") or "").strip()
    except Exception:
        current_app.logger.exception("roadmap generation failed")
        steps = steps_for_startup(None)

    startup = Startup(
        name=name,
        tagline=tagline,
        stage=steps[0]["label"],
        roadmap_step=0,
        roadmap_steps_json=dump_steps(steps),
        roadmap_started_at=datetime.now(timezone.utc),
        traction=8,
        health=20,
        owner_id=user.id,
    )
    db.session.add(startup)
    db.session.flush()

    thread.phase = "roadmap"
    thread.startup_id = startup.id
    thread.title = name
    db.session.add(thread)
    db.session.commit()

    launch_reply = (
        f"Идея принята. Проект «{name}» — карта из {len(steps)} шагов к деньгам. "
        f"Старт: «{steps[0]['label']}»."
    )
    if plan_summary:
        launch_reply += f" {plan_summary}"
    add_message(thread, "assistant", launch_reply)

    threads = threads_for_user(user)
    progress_url = url_for("main.progress_page", startup=startup.id)
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Redirect": progress_url}
    return redirect(progress_url)


@bp.post("/ai/chat")
@bp.post("/ai/roast")
def ai_chat():
    user = session_user()
    if not user:
        return render_template("partials/chat_error.html", error="Войди в аккаунт."), 401
    from ..services.ai_limits import can_use_ai, consume_ai_request

    if not can_use_ai(user):
        return render_template(
            "partials/chat_error.html",
            error="Лимит AI-запросов на месяц исчерпан. Обнови тариф или подожди.",
        ), 429
    form = ChatForm()
    if not form.validate_on_submit():
        return render_template("partials/chat_error.html", error="Напиши сообщение подлиннее."), 422

    message = form.message.data.strip()
    thread = resolve_thread(user, _thread_id_from_form(form))
    if not thread:
        thread = create_thread(user)

    if thread.phase == "roadmap" and not thread.startup_id:
        thread.phase = "roast"

    add_message(thread, "user", message)
    history = history_for_thread(thread)
    startup = db.session.get(Startup, thread.startup_id) if thread.startup_id else None
    step_notice = None
    roast = None
    show_validate = False

    force_roast = request.form.get("force_roast") == "1"
    via_map = request.form.get("via_map") == "1"
    if force_roast:
        thread.phase = "roast"

    map_startup = startup or progress_startup_for(user, thread)
    if via_map and map_startup and not force_roast:
        startup = map_startup
        if not thread.startup_id:
            thread.startup_id = startup.id
        thread.phase = "roadmap"
        db.session.add(thread)
        db.session.commit()

    map_notice = None
    suggest_via_map = False
    map_hint = ""
    ask_map_confirm = False
    map_confirm_hint = ""
    try:
        if via_map and map_startup and not force_roast:
            startup = map_startup
            steps = steps_for_startup(startup)
            if is_finished(startup.roadmap_step, steps):
                data = generate_roadmap_completed_turn(history, user, startup.name, steps)
                reply = data.get("reply", "")
            else:
                data = generate_roadmap_smart_turn(
                    history, user, startup.name, steps, startup.roadmap_step, startup.tagline
                )
                reply = data.get("reply", "")
                focus = data.get("focus_step_index", startup.roadmap_step)
                focus_step = steps[focus] if focus < len(steps) else steps[startup.roadmap_step]
                map_notice = f"Карта · шаг {focus + 1} из {len(steps)}: {focus_step['label']}"
                if data.get("step_complete"):
                    step_notice = (
                        "Чтобы закрыть шаг, заполни форму «Отчёт на проверку» ниже в чате — "
                        "сначала проверит AI, затем админ."
                    )
                    data["step_complete"] = False
                elif data.get("ask_map_confirm"):
                    ask_map_confirm = True
                    map_confirm_hint = (
                        "Поставь галочку «По карте прогресса» и отправь подтверждение, чтобы отметить на карте."
                    )
        elif map_startup and not force_roast:
            startup = map_startup
            steps = steps_for_startup(startup)
            data = generate_context_turn(
                history, user, startup.name, steps, startup.roadmap_step, startup.tagline
            )
            reply = data.get("reply", "")
            suggest_via_map = bool(data.get("suggest_via_map"))
            map_hint = (data.get("map_hint") or "").strip()
            if suggest_via_map and not map_hint:
                map_hint = "Включи «По карте прогресса» ниже — отвечу по нужному шагу ветки."
        else:
            thread.phase = "roast"
            data = generate_roast(history, user)
            reply = data.get("reply", "")
            roast = {
                "score": data.get("score", 0),
                "verdict": data.get("verdict", ""),
                "risks": data.get("risks", []),
                "alternatives": data.get("alternatives", []),
            }
            thread.idea_name = (data.get("idea_name") or "Новый проект")[:100]
            thread.idea_tagline = (data.get("idea_tagline") or message[:180])[:180]
            thread.roast_score = int(data.get("score") or 0)
            show_validate = bool(data.get("can_validate"))
            db.session.add(thread)
            db.session.commit()
            from ..services.achievements import check_and_grant

            check_and_grant(user, event="roast")
    except Exception:
        current_app.logger.exception("OpenAI chat failed")
        _rollback_last_user_message(thread, message)
        return render_template(
            "partials/chat_error.html",
            error="AI временно недоступен. Попробуй ещё раз через минуту.",
        ), 503

    add_message(thread, "assistant", reply)
    try:
        consume_ai_request(user)
    except Exception:
        pass
    try:
        summary = generate_thread_summary(history_for_thread(thread))
        update_thread_summary(thread, summary)
    except Exception:
        current_app.logger.exception("Thread summary failed")

    threads = threads_for_user(user)
    progress_url = None
    progress_startup = progress_startup_for(user, thread)
    if progress_startup:
        progress_url = url_for("main.progress_page", startup=progress_startup.id)
    return render_template(
        "partials/chat_reply.html",
        reply=reply,
        thread=thread,
        threads=threads,
        roast=roast,
        show_validate=show_validate and thread.phase == "roast",
        step_notice=step_notice,
        map_notice=map_notice,
        suggest_via_map=suggest_via_map,
        map_hint=map_hint,
        ask_map_confirm=ask_map_confirm,
        map_confirm_hint=map_confirm_hint,
        progress_url=progress_url,
        progress_startup=progress_startup,
        map_steps=steps_for_startup(progress_startup) if progress_startup else [],
    )


@bp.get("/startup/<int:startup_id>")
def startup_detail(startup_id: int):
    startup = db.session.get(Startup, startup_id) or abort(404)
    user = session_user()
    from ..services.team import is_team_member, startup_team_profile

    is_owner = bool(user and startup.owner_id == user.id)
    is_member = bool(user and is_team_member(startup.id, user.id))
    team_profile = startup_team_profile(startup) if is_owner or is_member else None
    activities = (
        Activity.query.filter_by(startup_id=startup.id).order_by(Activity.created_at.desc(), Activity.id.desc()).all()
    )
    feed_items = feed_items_for(activities, user)
    return render_template(
        "startup.html",
        startup=startup,
        owner=startup.owner,
        activities=activities,
        feed_items=feed_items,
        user=user,
        is_owner=is_owner,
        is_member=is_member,
        team_profile=team_profile,
        active_tab="profile" if user and (is_owner or is_member) else "home",
    )


@bp.get("/profile")
def profile():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    return render_user_profile(user)


def render_user_profile(profile_user: User, *, active_tab: str = "profile"):
    viewer = session_user()
    is_own_profile = bool(viewer and viewer.id == profile_user.id)
    team = profile_team_context(profile_user, viewer) if not is_investor(profile_user) else None
    return render_template(
        "profile.html",
        user=profile_user,
        is_own_profile=is_own_profile,
        is_investor_profile=is_investor(profile_user),
        my_startups=user_startups(profile_user),
        team=team,
        active_tab=active_tab if is_own_profile else "leaderboard",
    )


@bp.get("/users/<int:user_id>")
def user_profile(user_id: int):
    profile_user = db.session.get(User, user_id) or abort(404)
    return render_user_profile(profile_user, active_tab="leaderboard")


@bp.get("/profile/edit")
def profile_edit():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))

    from ..routes.auth import PhoneChangeForm

    form = ProfileForm(role=role_id_for_user(user.role))
    form.name.data = user.name
    phone_form = PhoneChangeForm()
    _, startups, _, _, _, active_startup = dashboard_data()
    investor = is_investor(user)
    from ..services.achievements import achievements_for

    return render_template(
        "profile_edit.html",
        form=form,
        phone_form=phone_form,
        user=user,
        roles=founder_roles(),
        selected_role=role_id_for_user(user.role),
        show_role_picker=not investor,
        active_startup=active_startup,
        achievements=achievements_for(user),
        active_tab="profile",
    )


@bp.post("/profile/edit")
def profile_edit_submit():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))

    form = ProfileForm()
    if is_investor(user):
        form.role.data = "investor"
    avatar_error = None
    upload = request.files.get("avatar")

    if not form.validate_on_submit():
        _, startups, _, _, _, active_startup = dashboard_data()
        return render_template(
            "profile_edit.html",
            form=form,
            user=user,
            roles=founder_roles(),
            selected_role=form.role.data or role_id_for_user(user.role),
            show_role_picker=not is_investor(user),
            avatar_error=avatar_error,
            active_startup=active_startup,
            active_tab="profile",
        ), 422

    user.name = form.name.data.strip()
    if is_investor(user):
        user.role = INVESTOR_ROLE_LABEL
    else:
        user.role = role_label_for_id(form.role.data)
    user.avatar = (user.name[:1] or "K").upper()

    if form.remove_avatar.data:
        delete_avatar_files(user.id)
        user.avatar_url = None
    elif upload and upload.filename:
        try:
            user.avatar_url = save_avatar_file(user.id, upload)
        except ValueError as exc:
            avatar_error = str(exc)
            db.session.rollback()
            _, startups, _, _, _, active_startup = dashboard_data()
            return render_template(
                "profile_edit.html",
                form=form,
                user=user,
                roles=founder_roles(),
                selected_role=form.role.data,
                show_role_picker=not is_investor(user),
                avatar_error=avatar_error,
                active_startup=active_startup,
                active_tab="profile",
            ), 422
    elif find_avatar_file(user.id):
        user.avatar_url = f"/uploads/avatars/{user.id}"

    db.session.commit()
    flash("Профиль сохранён", "success")
    return redirect(url_for("main.profile"))
