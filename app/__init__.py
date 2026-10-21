import os
from pathlib import Path

from flask import Flask, render_template, url_for

from app.extensions import csrf, db, limiter, login_manager
from config import CONFIGS


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    """Application factory: tests can build an isolated app with config_name='testing'."""
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    config_class = CONFIGS.get(config_name, CONFIGS["development"])

    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config.update(overrides or {})

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Add it to your environment or .env file.")

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to see that page."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"

    from app import models
    from app.admin import bp as admin_bp
    from app.auth import bp as auth_bp
    from app.bookings import bp as bookings_bp
    from app.cli import create_admin_command, reset_db_command, security_scan_command, seed_command
    from app.flights import bp as flights_bp
    from app.main import bp as main_bp

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(models.User, int(user_id)) if user_id.isdigit() else None

    for blueprint in (main_bp, flights_bp, auth_bp, bookings_bp, admin_bp):
        app.register_blueprint(blueprint)
    for command in (seed_command, reset_db_command, create_admin_command, security_scan_command):
        app.cli.add_command(command)

    with app.app_context():
        db.create_all()  # adds any missing tables; never touches existing data

    register_template_helpers(app)
    register_error_handlers(app)
    return app


def register_template_helpers(app: Flask) -> None:
    @app.template_global()
    def photo_url(slug: str) -> str | None:
        """URL of static/img/destinations/<slug>.jpg, or None if no photo was added yet.

        The slug always comes from our own database, never from the visitor.
        """
        photo = Path(app.static_folder) / "img" / "destinations" / f"{slug}.jpg"
        if photo.is_file():
            return url_for("static", filename=f"img/destinations/{slug}.jpg")
        return None


def register_error_handlers(app: Flask) -> None:
    # SR12: friendly error pages that never reveal stack traces or internals.
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def too_many_requests(_error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("errors/500.html"), 500