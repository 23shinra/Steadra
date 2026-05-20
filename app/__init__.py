from urllib.parse import urlsplit, urlunsplit

from flask import Flask, redirect, request
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

from config import Config

from .models import db
from .routes.auth import bp as auth_bp

csrf = CSRFProtect()
migrate = Migrate()


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_class)

    @app.before_request
    def canonicalize_host():
        # Trailing dot in host (e.g. "kangaroo.esl.kz.") breaks cookies/CSRF in practice
        # when users bounce between dotted/undotted hostnames.
        host = (request.host or "").strip()
        if host.endswith("."):
            new_host = host.rstrip(".")
            parts = urlsplit(request.url)
            new_url = urlunsplit((parts.scheme, new_host, parts.path, parts.query, parts.fragment))
            return redirect(new_url, code=308)

    db.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from .routes.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    @app.context_processor
    def inject_current_user():
        from .routes.auth import current_user as _cu

        return {"current_user": _cu()}

    # Prototype convenience: ensure tables exist without running migrations.
    with app.app_context():
        db.create_all()

    return app

