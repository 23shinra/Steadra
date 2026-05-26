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

    db.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    def get_locale():
        from flask import request, session
        from .routes.auth import session_user

        user = session_user()
        if user and getattr(user, "locale", None):
            return user.locale
        return session.get("locale") or request.accept_languages.best_match(
            app.config.get("BABEL_SUPPORTED_LOCALES", ["ru"])
        )

    babel.init_app(app, locale_selector=get_locale)

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

    @app.context_processor
    def inject_account_context():
        from flask import request

        from .access import is_investor
        from .routes.auth import session_user
        from .services.ai_limits import ai_remaining
        from .services.notifications import unread_count

        user = session_user()
        endpoint = request.endpoint or ""
        return {
            "is_investor_user": is_investor(user),
            "session_user": user,
            "unread_notif_count": unread_count(user),
            "vapid_public_key": app.config.get("VAPID_PUBLIC_KEY", ""),
            "is_admin": endpoint.startswith("admin."),
            "ai_remaining": ai_remaining(user) if user else None,
            "supported_locales": app.config.get("LANGUAGES", {}),
            "current_locale": get_locale(),
        }

    @app.template_filter("user_role")
    def user_role_filter(value):
        from .roles import display_role

        return display_role(value)

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

    with app.app_context():
        db.create_all()
        from .models.seed import ensure_feed_schema, seed_demo_data

        ensure_feed_schema()
        seed_demo_data()

    return app
