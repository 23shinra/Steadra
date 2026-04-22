from __future__ import annotations

import secrets
from datetime import datetime

from flask import Blueprint, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..forms import CodeForm, PasswordForm, PhoneForm, SkillsForm
from ..models import db
from ..models.entities import AuthSession, User

bp = Blueprint("auth", __name__)

COOKIE_NAME = "steadra_session"


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _hx_redirect(location: str):
    # HTMX-friendly redirect
    resp = make_response("", 200)
    resp.headers["HX-Redirect"] = location
    return resp


def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits and not digits.startswith("+"):
        digits = "+" + digits
    return digits


def current_user() -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    s = AuthSession.query.filter_by(token=token, revoked_at=None).first()
    if not s:
        return None
    s.last_seen_at = datetime.utcnow()
    db.session.commit()
    return db.session.get(User, s.user_id)


@bp.get("/logout")
def logout():
    token = request.cookies.get(COOKIE_NAME)
    if token:
        s = AuthSession.query.filter_by(token=token, revoked_at=None).first()
        if s:
            s.revoked_at = datetime.utcnow()
            db.session.commit()
    resp = redirect(url_for("auth.start"))
    resp.delete_cookie(COOKIE_NAME)
    return resp


@bp.get("/auth")
def start():
    # If already authed, go straight to chat
    if current_user():
        return redirect(url_for("main.ui_tab", tab="chat"))
    form = PhoneForm()
    tpl = "auth/start.html" if not _is_htmx() else "auth/partials/phone.html"
    return render_template(tpl, form=form, hide_nav=True)


@bp.post("/auth/phone")
def submit_phone():
    form = PhoneForm()
    if not form.validate_on_submit():
        return render_template("auth/partials/phone.html", form=form, hide_nav=True)

    phone = _normalize_phone(form.phone.data)
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) != 11 or not digits.startswith("7"):
        form.phone.errors.append("Введите номер в формате +7 (XXX) XXX-XX-XX")
        return render_template("auth/partials/phone.html", form=form, hide_nav=True)
    session["auth_phone"] = phone
    session["auth_sms_ok"] = False

    # In real life: send SMS. For prototype: code is 1234.
    if _is_htmx():
        return _hx_redirect(url_for("auth.code"))
    return redirect(url_for("auth.code"))


@bp.get("/auth/code")
def code():
    if current_user():
        return redirect(url_for("main.ui_tab", tab="chat"))
    if not session.get("auth_phone"):
        return redirect(url_for("auth.start"))
    form = CodeForm()
    tpl = "auth/code.html" if not _is_htmx() else "auth/partials/code.html"
    return render_template(tpl, form=form, phone=session.get("auth_phone"), hide_nav=True)


@bp.post("/auth/code")
def submit_code():
    if not session.get("auth_phone"):
        return redirect(url_for("auth.start"))
    form = CodeForm()
    if not form.validate_on_submit():
        return render_template("auth/partials/code.html", form=form, phone=session.get("auth_phone"), hide_nav=True)

    if form.code.data.strip() != "1234":
        form.code.errors.append("Неверный код. Для теста используйте 1234.")
        return render_template("auth/partials/code.html", form=form, phone=session.get("auth_phone"), hide_nav=True)

    session["auth_sms_ok"] = True
    if _is_htmx():
        return _hx_redirect(url_for("auth.password"))
    return redirect(url_for("auth.password"))


@bp.get("/auth/password")
def password():
    if current_user():
        return redirect(url_for("main.ui_tab", tab="chat"))
    if not session.get("auth_phone") or not session.get("auth_sms_ok"):
        return redirect(url_for("auth.start"))
    form = PasswordForm()
    tpl = "auth/password.html" if not _is_htmx() else "auth/partials/password.html"
    return render_template(tpl, form=form, phone=session.get("auth_phone"), hide_nav=True)


@bp.post("/auth/password")
def submit_password():
    if not session.get("auth_phone") or not session.get("auth_sms_ok"):
        return redirect(url_for("auth.start"))
    phone = session["auth_phone"]

    form = PasswordForm()
    if not form.validate_on_submit():
        return render_template("auth/partials/password.html", form=form, phone=phone, hide_nav=True)

    user = User.query.filter_by(phone=phone).first()
    if user and user.password_hash:
        if not check_password_hash(user.password_hash, form.password.data):
            form.password.errors.append("Неверный пароль.")
            return render_template("auth/partials/password.html", form=form, phone=phone, hide_nav=True)
        # If user already completed profile, skip skills step.
        if user.full_name and user.skills:
            token = secrets.token_urlsafe(32)
            db_sess = AuthSession(token=token, user_id=user.id)
            db.session.add(db_sess)
            db.session.commit()

            session.pop("auth_phone", None)
            session.pop("auth_sms_ok", None)
            session.pop("auth_user_id", None)

            resp = _hx_redirect(url_for("main.ui_tab", tab="chat")) if _is_htmx() else redirect(url_for("main.ui_tab", tab="chat"))
            resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
            return resp
    else:
        if not user:
            user = User(phone=phone, full_name="")
            db.session.add(user)
        user.password_hash = generate_password_hash(form.password.data)
        db.session.commit()

    session["auth_user_id"] = user.id
    if _is_htmx():
        return _hx_redirect(url_for("auth.skills"))
    return redirect(url_for("auth.skills"))


@bp.get("/auth/skills")
def skills():
    if current_user():
        return redirect(url_for("main.ui_tab", tab="chat"))
    if not session.get("auth_user_id"):
        return redirect(url_for("auth.start"))
    user = db.session.get(User, session["auth_user_id"])
    if user and user.full_name and user.skills:
        return redirect(url_for("main.ui_tab", tab="chat"))
    form = SkillsForm()
    if user:
        form.full_name.data = user.full_name or ""
        form.skills.data = [s.strip() for s in (user.skills or "").split(",") if s.strip()]
    tpl = "auth/skills.html" if not _is_htmx() else "auth/partials/skills.html"
    return render_template(tpl, form=form, hide_nav=True)


@bp.post("/auth/skills")
def submit_skills():
    if not session.get("auth_user_id"):
        return redirect(url_for("auth.start"))
    form = SkillsForm()
    if not form.validate_on_submit():
        return render_template("auth/partials/skills.html", form=form, hide_nav=True)

    user = db.session.get(User, session["auth_user_id"])
    if not user:
        return redirect(url_for("auth.start"))

    user.full_name = form.full_name.data.strip()
    user.skills = ", ".join(form.skills.data)
    db.session.commit()

    token = secrets.token_urlsafe(32)
    db_sess = AuthSession(token=token, user_id=user.id)
    db.session.add(db_sess)
    db.session.commit()

    # Clear temporary auth flow state
    session.pop("auth_phone", None)
    session.pop("auth_sms_ok", None)
    session.pop("auth_user_id", None)

    resp = _hx_redirect(url_for("main.ui_tab", tab="chat")) if _is_htmx() else redirect(url_for("main.ui_tab", tab="chat"))
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
    return resp

