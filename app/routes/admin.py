import re
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from ..access import ACCOUNT_INVESTOR, ACCOUNT_USER, normalize_account_type, ACCOUNT_TYPES, account_type_label
from ..roles import INVESTOR_ROLE_LABEL, ROLE_LABELS, founder_roles, role_id_for_user, role_label_for_id
from ..models import db
from ..models.entities import Activity, AiMessage, AiThread, Notification, Partner, PushSubscription, Startup, StepValidationRequest, TooValidationRequest, User
from ..services.roadmap import ROADMAP_STEPS, too_status, steps_for_startup, step_logs_by_index
from ..services.step_validation import admin_approve, admin_reject, pending_admin_queue
from ..services.too_validation import (
    admin_approve_too,
    admin_reject_too,
    pending_too_queue,
    too_validation_bundle,
)
from ..services.validation_admin import validation_bundle, validation_queue_bundles
from ..services.admin_users import (
    admin_interaction_stats,
    admin_onboarding_funnel,
    admin_recent_invitations,
    admin_retention_stats,
    admin_startup_progress,
    admin_stuck_founders,
    admin_teams_overview,
    admin_user_detail,
    admin_user_progress_summary,
    admin_user_retention_detail,
    admin_user_stuck_summary,
    admin_user_step_summary,
    admin_user_team_summary,
)
from ..services.partners import ensure_partners

bp = Blueprint("admin", __name__, url_prefix="/admin")


class AdminPhoneForm(FlaskForm):
    phone = StringField("Телефон", validators=[DataRequired()])


class AdminOtpForm(FlaskForm):
    phone = StringField(validators=[DataRequired()])
    code = StringField("Код из сообщения", validators=[DataRequired(), Length(min=4, max=6)])


class AdminUserEditForm(FlaskForm):
    name = StringField("Имя", validators=[DataRequired(), Length(min=2, max=80)])
    phone = StringField("Телефон", validators=[DataRequired(), Length(min=10, max=32)])
    account_type = SelectField(
        "Тип аккаунта",
        choices=[(ACCOUNT_USER, "Основатель"), (ACCOUNT_INVESTOR, "Инвестор")],
        validators=[DataRequired()],
    )
    role = SelectField("Роль", validators=[DataRequired()])
    age = IntegerField("Возраст", validators=[Optional(), NumberRange(min=14, max=99)])
    experience_years = IntegerField("Лет опыта", validators=[Optional(), NumberRange(min=0, max=60)])
    experience_text = TextAreaField("Опыт (текст)", validators=[Optional(), Length(max=900)])
    score = IntegerField("XP", validators=[Optional(), NumberRange(min=0, max=999999)])
    streak = IntegerField("Streak", validators=[Optional(), NumberRange(min=0, max=9999)])
    onboarding_done = BooleanField("Онбординг пройден")
    is_verified_investor = BooleanField("Проверенный инвестор")
    is_premium = BooleanField("Premium (безлимит AI)")

    def __init__(self, *args, user_id: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id
        self.role.choices = [(INVESTOR_ROLE_LABEL, INVESTOR_ROLE_LABEL)] + [
            (role["label"], role["label"]) for role in founder_roles()
        ]

    def validate_phone(self, field):
        phone = field.data.strip()
        if not phone:
            raise ValidationError("Укажи телефон.")
        existing = User.query.filter(User.phone == phone, User.id != self.user_id).first()
        if existing:
            raise ValidationError("Этот телефон уже занят.")


_STEP_KEY_CHOICES = [("", "Любой шаг")] + [(s["key"], s["label"]) for s in ROADMAP_STEPS]


class AdminPartnerForm(FlaskForm):
    name = StringField("Название", validators=[DataRequired(), Length(min=2, max=120)])
    category = SelectField(
        "Категория",
        choices=[
            ("accelerator", "Акселератор"),
            ("investor", "Инвестор"),
            ("gov", "Гос"),
            ("finance", "Финансы"),
            ("service", "Сервис"),
        ],
        validators=[DataRequired()],
    )
    description = TextAreaField("Описание", validators=[Optional(), Length(max=900)])
    url = StringField("URL", validators=[Optional(), Length(max=500)])
    region = StringField("Регион", validators=[Optional(), Length(max=80)])
    roadmap_step_key = SelectField("Шаг карты", choices=_STEP_KEY_CHOICES, validators=[Optional()])
    sort_order = IntegerField("Порядок", validators=[Optional(), NumberRange(min=0, max=9999)], default=0)
    active = BooleanField("Активен", default=True)

def _normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def is_admin_phone(raw: str) -> bool:
    digits = _normalize_phone(raw)
    configured = _normalize_phone(current_app.config.get("ADMIN_PHONE", ""))
    return bool(configured) and digits == configured


def admin_logged_in() -> bool:
    return session.get("admin") is True


def _apply_account_type_rules(user: User) -> None:
    user.account_type = normalize_account_type(user.account_type)
    if user.account_type == ACCOUNT_INVESTOR:
        user.experience_years = None
        user.experience_text = None
        user.score = 0
        user.role = INVESTOR_ROLE_LABEL
    else:
        user.is_verified_investor = False
        if user.role == INVESTOR_ROLE_LABEL:
            user.role = "Основатель"


@bp.before_request
def require_admin():
    if request.endpoint in {"admin.login", "admin.submit_login", "admin.verify_login"}:
        return None
    if admin_logged_in():
        return None
    return redirect(url_for("admin.login"))


@bp.context_processor
def admin_template_context():
    endpoint = request.endpoint or ""
    if not endpoint.startswith("admin.") or endpoint in {"admin.login", "admin.submit_login", "admin.verify_login"}:
        return {}
    validation_endpoints = {
        "admin.validation_page",
        "admin.validation_detail",
        "admin.validation_evidence",
        "admin.validation_approve",
        "admin.validation_reject",
    }
    too_endpoints = {
        "admin.validation_too_page",
        "admin.validation_too_detail",
        "admin.validation_too_evidence",
        "admin.validation_too_approve",
        "admin.validation_too_reject",
    }
    partner_endpoints = {
        "admin.partners_page",
        "admin.partner_create",
        "admin.partner_edit",
        "admin.partner_toggle",
    }
    nav = "dashboard"
    if endpoint in validation_endpoints:
        nav = "validation"
    elif endpoint in too_endpoints:
        nav = "validation_too"
    elif endpoint in partner_endpoints:
        nav = "partners"
    return {
        "pending_count": len(pending_admin_queue(100)),
        "pending_too_count": len(pending_too_queue(100)),
        "admin_nav": nav,
    }


@bp.get("/login")
def login():
    if admin_logged_in():
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html", form=AdminPhoneForm(), hide_nav=True)


@bp.post("/login")
def submit_login():
    form = AdminPhoneForm()
    if not form.validate_on_submit():
        return render_template("admin/_phone_form.html", form=form), 422

    if not is_admin_phone(form.phone.data):
        form.phone.errors.append("Неверный номер для админки.")
        return render_template("admin/_phone_form.html", form=form), 422

    from ..services.otp import normalize_phone, send_otp

    phone = normalize_phone(form.phone.data)
    purpose = current_app.config.get("OTP_PURPOSE_LOGIN") or "login"
    ok, error_or_hint = send_otp(phone, purpose=purpose)
    if not ok:
        form.phone.errors.append(error_or_hint or "Не удалось отправить код.")
        return render_template("admin/_phone_form.html", form=form), 422

    session["pending_admin_phone"] = phone
    otp_form = AdminOtpForm(phone=phone)
    return render_template(
        "admin/_otp_form.html",
        form=otp_form,
        phone=phone,
        demo_hint=error_or_hint,
    )


@bp.post("/login/verify")
def verify_login():
    from ..services.otp import normalize_phone, verify_otp

    form = AdminOtpForm()
    pending = session.get("pending_admin_phone")
    if (
        not form.validate_on_submit()
        or not pending
        or normalize_phone(form.phone.data or "") != pending
    ):
        phone_form = AdminPhoneForm()
        phone_form.phone.errors.append("Запроси код заново.")
        return render_template("admin/_phone_form.html", form=phone_form), 422
    if not is_admin_phone(pending):
        abort(403)

    from ..security import rotate_session

    purpose = current_app.config.get("OTP_PURPOSE_LOGIN") or "login"
    ok, error = verify_otp(pending, form.code.data, purpose=purpose)
    if not ok:
        form.code.errors.append(error or "Неверный или просроченный код.")
        return render_template("admin/_otp_form.html", form=form, phone=pending), 422

    user_id = session.get("user_id")
    rotate_session(admin=True, user_id=user_id)
    target = url_for("admin.dashboard")
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Redirect": target}
    return redirect(target)


@bp.post("/logout")
def logout():
    session.pop("admin", None)
    session.pop("pending_admin_phone", None)
    return redirect(url_for("admin.login"))


@bp.get("/")
@bp.get("/dashboard")
def dashboard():
    users = User.query.order_by(User.id.desc()).all()
    startups = Startup.query.order_by(Startup.id.desc()).all()
    threads = AiThread.query.order_by(AiThread.updated_at.desc()).limit(50).all()
    activities = Activity.query.order_by(Activity.created_at.desc()).limit(50).all()
    push_subscriptions = PushSubscription.query.order_by(PushSubscription.created_at.desc()).limit(50).all()
    unread_notifications = (
        Notification.query.filter(Notification.read_at.is_(None))
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    stats = {
        "users": User.query.count(),
        "startups": Startup.query.count(),
        "threads": AiThread.query.count(),
        "messages": AiMessage.query.count(),
        "activities": Activity.query.count(),
    }
    stats.update(admin_interaction_stats())
    stats.update(admin_retention_stats())
    startup_rows = {s.id: admin_startup_progress(s) for s in startups}
    return render_template(
        "admin/dashboard.html",
        hide_nav=True,
        stats=stats,
        users=users,
        startups=startups,
        startup_rows=startup_rows,
        threads=threads,
        activities=activities,
        push_subscriptions=push_subscriptions,
        unread_notifications=unread_notifications,
        teams=admin_teams_overview(),
        invitations=admin_recent_invitations(25),
        stuck_founders=admin_stuck_founders(7),
        onboarding_funnel=admin_onboarding_funnel(),
        pending_validations=pending_admin_queue(20),
        account_types=ACCOUNT_TYPES,
        account_type_label=account_type_label,
        admin_user_progress_summary=admin_user_progress_summary,
        admin_user_stuck_summary=admin_user_stuck_summary,
        admin_user_step_summary=admin_user_step_summary,
        admin_user_team_summary=admin_user_team_summary,
        founder_roles=founder_roles(),
    )


@bp.get("/users/<int:user_id>")
def user_detail(user_id: int):
    user = User.query.get_or_404(user_id)
    return render_template(
        "admin/user_detail.html",
        hide_nav=True,
        user=user,
        detail=admin_user_detail(user),
        retention=admin_user_retention_detail(user),
        account_type_label=account_type_label,
    )


@bp.get("/threads/<int:thread_id>")
def thread_detail(thread_id: int):
    thread = AiThread.query.get_or_404(thread_id)
    user = thread.user
    messages = (
        AiMessage.query.filter_by(thread_id=thread.id)
        .order_by(AiMessage.created_at.asc(), AiMessage.id.asc())
        .all()
    )
    too = {"state": "unknown", "label": "—"}
    if thread.startup:
        steps = steps_for_startup(thread.startup)
        logs = step_logs_by_index(thread.startup)
        too = too_status(thread.startup, steps, logs)
    return render_template(
        "admin/thread_detail.html",
        hide_nav=True,
        thread=thread,
        user=user,
        messages=messages,
        too=too,
        account_type_label=account_type_label,
    )


@bp.get("/users/<int:user_id>/edit")
def edit_user(user_id: int):
    user = User.query.get_or_404(user_id)
    form = AdminUserEditForm(user_id=user.id)
    form.name.data = user.name
    form.phone.data = user.phone
    form.account_type.data = user.account_type
    form.role.data = user.role if user.account_type == ACCOUNT_INVESTOR else role_label_for_id(role_id_for_user(user.role))
    form.age.data = user.age
    form.experience_years.data = user.experience_years
    form.experience_text.data = user.experience_text or ""
    form.score.data = user.score
    form.streak.data = user.streak
    form.onboarding_done.data = user.onboarding_done
    form.is_verified_investor.data = bool(user.is_verified_investor)
    form.is_premium.data = bool(getattr(user, "is_premium", False))
    return render_template(
        "admin/user_edit.html",
        hide_nav=True,
        user=user,
        form=form,
    )


@bp.post("/users/<int:user_id>/edit")
def edit_user_submit(user_id: int):
    user = User.query.get_or_404(user_id)
    form = AdminUserEditForm(user_id=user.id)
    if not form.validate_on_submit():
        return render_template(
            "admin/user_edit.html",
            hide_nav=True,
            user=user,
            form=form,
        ), 422

    user.name = form.name.data.strip()
    user.phone = form.phone.data.strip()
    user.account_type = normalize_account_type(form.account_type.data)
    if user.account_type == ACCOUNT_INVESTOR:
        user.role = INVESTOR_ROLE_LABEL
    else:
        user.role = form.role.data
    user.age = form.age.data
    user.experience_years = form.experience_years.data
    user.experience_text = (form.experience_text.data or "").strip() or None
    user.score = form.score.data or 0
    user.streak = form.streak.data or 0
    user.onboarding_done = bool(form.onboarding_done.data)
    user.is_verified_investor = bool(form.is_verified_investor.data) and user.account_type == ACCOUNT_INVESTOR
    user.is_premium = bool(form.is_premium.data)
    _apply_account_type_rules(user)
    db.session.commit()
    flash("Пользователь сохранён.", "success")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@bp.post("/users/<int:user_id>/role")
def set_user_role(user_id: int):
    user = User.query.get_or_404(user_id)
    user.account_type = normalize_account_type(request.form.get("account_type"))
    _apply_account_type_rules(user)
    db.session.commit()
    if request.headers.get("HX-Request"):
        return render_template(
            "admin/_user_role_cell.html",
            user=user,
            account_types=ACCOUNT_TYPES,
            account_type_label=account_type_label,
            founder_roles=founder_roles(),
        )
    return redirect(url_for("admin.dashboard"))


@bp.post("/users/<int:user_id>/founder-role")
def set_user_founder_role(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.account_type == ACCOUNT_INVESTOR:
        return redirect(url_for("admin.dashboard"))
    role_label = (request.form.get("founder_role") or "").strip()
    if role_label in ROLE_LABELS and role_label != INVESTOR_ROLE_LABEL:
        user.role = role_label
        db.session.commit()
    if request.headers.get("HX-Request"):
        return render_template(
            "admin/_user_role_cell.html",
            user=user,
            account_types=ACCOUNT_TYPES,
            account_type_label=account_type_label,
            founder_roles=founder_roles(),
        )
    return redirect(url_for("admin.dashboard"))


@bp.get("/validation")
@bp.get("/validations")
def validation_page():
    bundles = validation_queue_bundles(100)
    return render_template(
        "admin/validation.html",
        hide_nav=True,
        bundles=bundles,
        pending_count=len(bundles),
    )


@bp.get("/validation/too")
def validation_too_page():
    items = pending_too_queue(100)
    bundles = [too_validation_bundle(item) for item in items]
    return render_template(
        "admin/validation_too.html",
        hide_nav=True,
        bundles=bundles,
    )


@bp.get("/validation/too/<int:request_id>")
def validation_too_detail(request_id: int):
    req = TooValidationRequest.query.get_or_404(request_id)
    bundle = too_validation_bundle(req)
    return render_template(
        "admin/validation_too_detail.html",
        hide_nav=True,
        bundle=bundle,
        req=req,
        startup=bundle["startup"],
        user=bundle["user"],
        too=bundle["too"],
        chat_messages=bundle["chat_messages"],
        current_step=bundle["current_step"],
    )


@bp.get("/validation/too/evidence/<int:request_id>")
def validation_too_evidence(request_id: int):
    req = TooValidationRequest.query.get_or_404(request_id)
    if not req.evidence_filepath:
        abort(404)
    from ..security import send_contained_file
    from ..services.step_validation import evidence_root

    return send_contained_file(
        evidence_root(),
        Path(req.evidence_filepath),
        req.evidence_filename,
    )


@bp.post("/validation/too/<int:request_id>/approve")
def validation_too_approve(request_id: int):
    req = TooValidationRequest.query.get_or_404(request_id)
    notes = request.form.get("admin_notes", "")
    msg = admin_approve_too(req, admin_id=None, notes=notes)
    flash(msg, "success")
    return redirect(url_for("admin.validation_too_page"))


@bp.post("/validation/too/<int:request_id>/reject")
def validation_too_reject(request_id: int):
    req = TooValidationRequest.query.get_or_404(request_id)
    notes = request.form.get("admin_notes", "")
    msg = admin_reject_too(req, admin_id=None, notes=notes)
    flash(msg, "info")
    return redirect(url_for("admin.validation_too_page"))


@bp.get("/validations/<int:request_id>")
def validation_detail(request_id: int):
    req = StepValidationRequest.query.get_or_404(request_id)
    bundle = validation_bundle(req)
    return render_template(
        "admin/validation_detail.html",
        hide_nav=True,
        bundle=bundle,
        req=req,
        startup=bundle["startup"],
        user=bundle["user"],
        too=bundle["too"],
        chat_messages=bundle["chat_messages"],
        documents=bundle["documents"],
    )


@bp.get("/validation/evidence/<int:request_id>")
def validation_evidence(request_id: int):
    req = StepValidationRequest.query.get_or_404(request_id)
    if not req.evidence_filepath:
        abort(404)
    from ..security import send_contained_file
    from ..services.step_validation import evidence_root

    return send_contained_file(
        evidence_root(),
        Path(req.evidence_filepath),
        req.evidence_filename,
    )


@bp.post("/validations/<int:request_id>/approve")
def validation_approve(request_id: int):
    req = StepValidationRequest.query.get_or_404(request_id)
    notes = request.form.get("admin_notes", "")
    msg = admin_approve(req, admin_id=None, notes=notes)
    flash(msg, "success")
    return redirect(url_for("admin.validation_page"))


@bp.post("/validations/<int:request_id>/reject")
def validation_reject(request_id: int):
    req = StepValidationRequest.query.get_or_404(request_id)
    notes = request.form.get("admin_notes", "")
    msg = admin_reject(req, admin_id=None, notes=notes)
    flash(msg, "info")
    return redirect(url_for("admin.validation_page"))


def _partner_from_form(partner: Partner, form: AdminPartnerForm) -> None:
    partner.name = form.name.data.strip()
    partner.category = form.category.data
    partner.description = (form.description.data or "").strip()
    partner.url = (form.url.data or "").strip() or None
    partner.region = (form.region.data or "").strip() or None
    partner.roadmap_step_key = (form.roadmap_step_key.data or "").strip() or None
    partner.sort_order = int(form.sort_order.data or 0)
    partner.active = bool(form.active.data)


@bp.get("/partners")
def partners_page():
    ensure_partners()
    partners = Partner.query.order_by(Partner.sort_order.asc(), Partner.id.asc()).all()
    form = AdminPartnerForm()
    return render_template(
        "admin/partners.html",
        hide_nav=True,
        partners=partners,
        form=form,
    )


@bp.post("/partners")
def partner_create():
    form = AdminPartnerForm()
    if not form.validate_on_submit():
        partners = Partner.query.order_by(Partner.sort_order.asc(), Partner.id.asc()).all()
        return render_template(
            "admin/partners.html",
            hide_nav=True,
            partners=partners,
            form=form,
        ), 422
    partner = Partner()
    _partner_from_form(partner, form)
    db.session.add(partner)
    db.session.commit()
    flash("Партнёр добавлен.", "success")
    return redirect(url_for("admin.partners_page"))


@bp.route("/partners/<int:partner_id>/edit", methods=["GET", "POST"])
def partner_edit(partner_id: int):
    partner = Partner.query.get_or_404(partner_id)
    form = AdminPartnerForm(obj=partner) if request.method == "GET" else AdminPartnerForm()
    if request.method == "GET":
        form.roadmap_step_key.data = partner.roadmap_step_key or ""
        return render_template(
            "admin/partner_edit.html",
            hide_nav=True,
            partner=partner,
            form=form,
        )
    if not form.validate_on_submit():
        return render_template(
            "admin/partner_edit.html",
            hide_nav=True,
            partner=partner,
            form=form,
        ), 422
    _partner_from_form(partner, form)
    db.session.commit()
    flash("Партнёр сохранён.", "success")
    return redirect(url_for("admin.partners_page"))


@bp.post("/partners/<int:partner_id>/toggle")
def partner_toggle(partner_id: int):
    partner = Partner.query.get_or_404(partner_id)
    partner.active = not partner.active
    db.session.commit()
    flash("Партнёр " + ("включён" if partner.active else "скрыт") + ".", "success")
    return redirect(url_for("admin.partners_page"))
