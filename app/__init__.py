from flask import Flask
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

