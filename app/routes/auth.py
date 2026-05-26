import re

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, ValidationError

from ..access import ACCOUNT_INVESTOR, is_investor, normalize_account_type
from ..models import db
from ..models.entities import User
from ..roles import ROLES, founder_roles, is_valid_role_id, role_id_for_user, role_label_for_id, INVESTOR_ROLE_LABEL
from ..services.otp import normalize_phone, send_otp, verify_otp

bp = Blueprint("auth", __name__)

EXPERIENCE_CHOICES = [
    (0, "Без коммерческого опыта"),
    (1, "До 1 года"),
    (2, "1–2 года"),
    (3, "3–5 лет"),
    (5, "5+ лет"),
]

REGIONS = [
    ("", "Не указан"),
    ("almaty", "Алматы"),
    ("astana", "Астана"),
    ("shymkent", "Шымкент"),
    ("karaganda", "Караганда"),
    ("other", "Другой регион"),
]


class PhoneForm(FlaskForm):
    phone = StringField("Телефон", validators=[DataRequired()])

    def validate_phone(self, field):
        digits = normalize_phone(field.data or "")
        field.data = digits
        if len(digits) != 11 or not digits.startswith("7"):
            raise ValidationError("Введите казахстанский номер: 11 цифр, начиная с 7.")


class OtpForm(FlaskForm):
    phone = StringField(validators=[DataRequired()])
    code = StringField("Код из SMS", validators=[DataRequired(), Length(min=4, max=6)])


class ProfileOnboardingForm(FlaskForm):
    name = StringField("Как тебя зовут?", validators=[DataRequired(), Length(min=2, max=80)])
    age = IntegerField("Сколько лет", validators=[DataRequired(), NumberRange(min=14, max=99)])
    role = StringField("Сфера", validators=[DataRequired()])
    experience_years = SelectField(
        "Опыт в выбранной сфере",
        choices=EXPERIENCE_CHOICES,
        coerce=int,
        validators=[DataRequired()],
    )
    experience_text = TextAreaField(
        "Чем занимался и что умеешь",
        validators=[DataRequired(), Length(min=10, max=1200)],
    )
    account_type = SelectField(
        "Тип аккаунта",
        choices=[("user", "Основатель"), ("investor", "Инвестор")],
        default="user",
    )
    investor_invite_code = StringField("Код приглашения инвестора", validators=[Length(max=40)])
    region = SelectField("Город / регион", choices=REGIONS, default="")
    investor_fund_name = StringField("Фонд / компания", validators=[Length(max=160)])
    investor_linkedin = StringField("LinkedIn", validators=[Length(max=255)])

    def validate_role(self, field):
        if self.account_type.data == "investor":
            return
        if not is_valid_role_id(field.data):
            raise ValidationError("Выбери сферу из списка.")

    def validate_investor_invite_code(self, field):
        if self.account_type.data != "investor":
            return
        from flask import current_app

        codes = {
            c.strip()
            for c in (current_app.config.get("INVESTOR_INVITE_CODES") or "").split(",")
            if c.strip()
        }
        if codes and (field.data or "").strip() not in codes:
            raise ValidationError("Неверный код приглашения для инвестора.")


class PhoneChangeForm(FlaskForm):
    new_phone = StringField("Новый телефон", validators=[DataRequired()])
    code = StringField("Код из SMS", validators=[DataRequired(), Length(min=4, max=6)])

    def validate_new_phone(self, field):
        digits = normalize_phone(field.data or "")
        field.data = digits
        if len(digits) != 11 or not digits.startswith("7"):
            raise ValidationError("Введите казахстанский номер: 11 цифр, начиная с 7.")
        existing = User.query.filter_by(phone=digits).first()
        if existing:
            raise ValidationError("Этот номер уже занят.")


def session_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def post_login_redirect():
    user = session_user()
    if user and not user.onboarding_done:
        return url_for("auth.profile_onboarding")
    if user and getattr(user, "account_type", "user") == "investor":
        return url_for("investor.candidates")
    return url_for("main.home")


@bp.get("/login")
@bp.get("/auth/code")
def login():
    form = PhoneForm()
    otp_form = None
    phone = session.pop("pending_phone", None)
    if phone:
        otp_form = OtpForm(phone=phone)
    return render_template(
        "auth/login.html",
        form=form,
        otp_form=otp_form,
        pending_phone=phone,
        hide_nav=True,
    )


@bp.post("/login")
@bp.post("/auth/code")
def submit_login():
    form = PhoneForm()
    if not form.validate_on_submit():
        return render_template("auth/_phone_form.html", form=form), 422

    phone = form.phone.data.strip()
    ok, error_or_code = send_otp(phone, purpose="login")
    if not ok:
        return render_template("auth/_phone_form.html", form=form, error=error_or_code), 422

    session["pending_phone"] = phone
    otp_form = OtpForm(phone=phone)
    demo_hint = error_or_code
    return render_template(
        "auth/_otp_form.html",
        otp_form=otp_form,
        phone=phone,
        demo_hint=demo_hint,
    )


@bp.post("/auth/verify")
def verify_login():
    form = OtpForm()
    if not form.validate_on_submit():
        return render_template("auth/_otp_form.html", otp_form=form, phone=form.phone.data), 422

    phone = normalize_phone(form.phone.data)
    if not verify_otp(phone, form.code.data, purpose="login"):
        return render_template(
            "auth/_otp_form.html",
            otp_form=form,
            phone=phone,
            error="Неверный или просроченный код.",
        ), 422

    session.pop("pending_phone", None)
    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(
            name="Founder",
            phone=phone,
            role="Founder",
            avatar="K",
            score=0,
            streak=0,
            onboarding_done=False,
        )
        db.session.add(user)
        db.session.commit()

    session["user_id"] = user.id
    target = post_login_redirect()
    if request.headers.get("HX-Request"):
        return "", 204, {"HX-Redirect": target}
    return redirect(target)


@bp.get("/onboarding/profile")
def profile_onboarding():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    if user.onboarding_done:
        return redirect(url_for("main.home"))
    form = ProfileOnboardingForm()
    if is_investor(user):
        form.role.data = "investor"
        form.account_type.data = "investor"
    else:
        form.role.data = role_id_for_user(user.role)
        form.account_type.data = "user"
    if user.name != "Founder":
        form.name.data = user.name
    return render_template(
        "auth/profile_onboarding.html",
        form=form,
        roles=founder_roles(),
        show_role_picker=not is_investor(user),
        is_investor_user=is_investor(user),
        hide_nav=True,
    )


@bp.post("/onboarding/profile")
def profile_onboarding_submit():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    form = ProfileOnboardingForm()
    wants_investor = form.account_type.data == "investor"
    if wants_investor:
        form.role.data = "investor"
        form.experience_years.data = 0
        form.experience_text.data = "—"
    if not form.validate_on_submit():
        return render_template(
            "auth/profile_onboarding.html",
            form=form,
            roles=founder_roles(),
            show_role_picker=not wants_investor,
            is_investor_user=wants_investor,
            hide_nav=True,
        ), 422

    name = form.name.data.strip()
    user.name = name
    user.avatar = (name[0] or "K").upper()
    user.age = form.age.data
    user.region = form.region.data or None
    user.account_type = normalize_account_type(
        ACCOUNT_INVESTOR if wants_investor else "user"
    )
    if wants_investor:
        user.role = INVESTOR_ROLE_LABEL
        user.experience_years = None
        user.experience_text = None
        user.investor_fund_name = (form.investor_fund_name.data or "").strip() or None
        user.investor_linkedin = (form.investor_linkedin.data or "").strip() or None
    else:
        user.role = role_label_for_id(form.role.data)
        user.experience_years = form.experience_years.data or 0
        user.experience_text = form.experience_text.data.strip()
    user.onboarding_done = True
    db.session.commit()
    if is_investor(user):
        return redirect(url_for("investor.candidates"))
    return redirect(url_for("main.ai", onboarding=1))


@bp.post("/profile/phone/request")
def phone_change_request():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    form = PhoneChangeForm()
    if not form.validate_on_submit():
        return render_template(
            "partials/phone_change_form.html",
            form=form,
            user=user,
            error=form.new_phone.errors[0] if form.new_phone.errors else "Проверь номер.",
        ), 422
    ok, error_or_code = send_otp(form.new_phone.data, purpose="phone_change")
    if not ok:
        return render_template(
            "partials/phone_change_form.html",
            form=form,
            user=user,
            error=error_or_code,
        ), 422
    session["pending_new_phone"] = form.new_phone.data
    return render_template(
        "partials/phone_change_form.html",
        form=form,
        user=user,
        code_sent=True,
        demo_hint=error_or_code,
        new_phone=form.new_phone.data,
    )


@bp.post("/profile/phone/confirm")
def phone_change_confirm():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    form = PhoneChangeForm()
    new_phone = session.get("pending_new_phone") or form.new_phone.data
    form.new_phone.data = new_phone
    if not form.validate_on_submit():
        return render_template(
            "partials/phone_change_form.html",
            form=form,
            user=user,
            code_sent=True,
            new_phone=new_phone,
            error=form.code.errors[0] if form.code.errors else "Проверь код.",
        ), 422
    if not verify_otp(new_phone, form.code.data, purpose="phone_change"):
        return render_template(
            "partials/phone_change_form.html",
            form=form,
            user=user,
            code_sent=True,
            new_phone=new_phone,
            error="Неверный или просроченный код.",
        ), 422
    user.phone = normalize_phone(new_phone)
    session.pop("pending_new_phone", None)
    db.session.commit()
    flash_msg = "Телефон обновлён."
    if request.headers.get("HX-Request"):
        return render_template(
            "partials/phone_change_form.html",
            form=PhoneChangeForm(),
            user=user,
            success=flash_msg,
        )
    from flask import flash

    flash(flash_msg, "success")
    return redirect(url_for("main.profile_edit"))


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.onboarding"))
