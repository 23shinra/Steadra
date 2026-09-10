from flask import Flask
from flask_babel import Babel
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

from config import Config
from .models import db

csrf = CSRFProtect()
migrate = Migrate()
babel = Babel()


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_class)
    if not app.testing:
        app.config["DEBUG"] = False

    db.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from .security import install_log_redaction, install_safe_jinja_config, install_security_headers

    install_security_headers(app)
    install_safe_jinja_config(app)
    install_log_redaction(app)

    def get_locale():
        from .services.i18n import get_request_locale

        return get_request_locale()

    babel.init_app(app, locale_selector=get_locale)

    @app.before_request
    def bind_request_locale():
        from flask import g, redirect, request

        from .services.i18n import get_request_locale, set_request_locale
        from .services.locale_urls import is_locale_exempt_path, locale_url_segment, path_with_locale

        env_locale = request.environ.get("kangaroo.locale")
        if env_locale:
            from .services.i18n import _normalize_locale

            code = _normalize_locale(env_locale)
            g.url_locale = code
            g.locale_segment = request.environ.get("kangaroo.locale_segment") or locale_url_segment(code)
            if request.method == "GET":
                set_request_locale(code)
        elif request.method == "GET" and not is_locale_exempt_path(request.path):
            locale = get_request_locale()
            g.locale_segment = locale_url_segment(locale)
            target = path_with_locale(
                request.path,
                locale,
                query_string=request.query_string.decode(),
            )
            if target != request.path:
                return redirect(target)

        g.user_locale = get_request_locale()
        if not getattr(g, "locale_segment", None):
            g.locale_segment = locale_url_segment(g.user_locale)

    from .routes.admin import bp as admin_bp
    from .routes.auth import bp as auth_bp
    from .routes.extensions import bp as extensions_bp
    from .routes.investor import bp as investor_bp
    from .routes.main import bp as main_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(extensions_bp)
    app.register_blueprint(investor_bp)
    app.register_blueprint(main_bp)

    from .services.locale_urls import LocalePrefixMiddleware

    app.wsgi_app = LocalePrefixMiddleware(app.wsgi_app)

    from .routes.extensions import admin_run_retention

    csrf.exempt(admin_run_retention)

    @app.context_processor
    def inject_account_context():
        from flask import request, session

        from .access import is_investor
        from .routes.auth import session_user
        from .services.ai_limits import ai_remaining
        from .services.messages import unread_dm_count
        from .services.notifications import unread_count

        user = session_user()
        endpoint = request.endpoint or ""

        def current_theme() -> str:
            if user and getattr(user, "theme", None) in {"dark", "light"}:
                return user.theme
            theme = session.get("theme", "dark")
            return theme if theme in {"dark", "light"} else "dark"

        from flask import g

        from .services.i18n import get_request_locale, translate
        from .services.locale_urls import localized_url_for

        locale = getattr(g, "user_locale", None) or get_request_locale()

        def url_for(endpoint, **values):
            return localized_url_for(endpoint, **values)

        return {
            "is_investor_user": is_investor(user),
            "session_user": user,
            "unread_notif_count": unread_count(user),
            "unread_dm_count": unread_dm_count(user),
            "vapid_public_key": app.config.get("VAPID_PUBLIC_KEY", ""),
            "is_admin": endpoint.startswith("admin."),
            "ai_remaining": ai_remaining(user) if user else None,
            "supported_locales": app.config.get("LANGUAGES", {}),
            "current_locale": locale,
            "current_theme": current_theme(),
            "allow_demo_login": bool(app.config.get("ALLOW_DEMO_LOGIN")),
            "tr": lambda key: translate(key, locale),
            "url_for": url_for,
        }

    @app.template_filter("roast_verdict")
    def roast_verdict_filter(verdict, score=None):
        from .services.startup_audit import polish_verdict

        return polish_verdict(verdict, score)

    @app.template_filter("user_role")
    def user_role_filter(value):
        from .roles import display_role

        return display_role(value)

    @app.template_filter("role_icon_name")
    def role_icon_name_filter(value):
        from .roles import icon_for_role

        return icon_for_role(value)

    @app.template_filter("startup_too")
    def startup_too_filter(startup):
        from .services.roadmap import step_logs_by_index, steps_for_startup, too_status

        if not startup:
            return {"state": "unknown", "label": "—"}
        steps = steps_for_startup(startup)
        return too_status(startup, steps, step_logs_by_index(startup))

    @app.template_filter("notification_kind")
    def notification_kind_filter(kind):
        from .services.notifications import notification_kind_label

        return notification_kind_label(kind)

    @app.template_filter("activity_kind")
    def activity_kind_filter(kind):
        from .services.feed_social import activity_kind_label

        return activity_kind_label(kind)

    @app.template_filter("thread_phase")
    def thread_phase_filter(phase):
        from .services.ai_threads import thread_phase_label

        return thread_phase_label(phase)

    # pass_context prevents Jinja from constant-folding |t at compile time
    # (otherwise the first request's locale gets baked into cached templates).
    from jinja2 import pass_context

    @app.template_filter("t")
    @pass_context
    def translate_filter(_ctx, key):
        from flask import g

        from .services.i18n import translate

        locale = getattr(g, "user_locale", None) or get_locale()
        return translate(key, locale)

    @app.template_filter("streak_days")
    @pass_context
    def streak_days_filter(_ctx, count):
        from flask import g

        from .services.i18n import streak_days_word

        locale = getattr(g, "user_locale", None) or get_locale()
        return streak_days_word(int(count or 0), locale)

    with app.app_context():
        db.create_all()
        from .models.seed import ensure_feed_schema, seed_demo_data

        ensure_feed_schema()
        seed_demo_data()

    return app
