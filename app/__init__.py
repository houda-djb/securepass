import os
from pathlib import Path

from flask import Flask, render_template, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import csrf, db, limiter, login_manager, migrate
from app.security_headers import init_security_headers
from config import CONFIGS

MIN_PRODUCTION_KEY_LENGTH = 32


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    """Application factory: tests can build an isolated app with config_name='testing'."""
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    config_class = CONFIGS.get(config_name, CONFIGS["development"])

    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config.update(overrides or {})

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Add it to your environment or .env file.")
    if config_name == "production" and len(app.config["SECRET_KEY"]) < MIN_PRODUCTION_KEY_LENGTH:
        raise RuntimeError("In production SECRET_KEY must be a random value of at least "
                           f"{MIN_PRODUCTION_KEY_LENGTH} characters.")

    if app.config["PROXY_HOPS"]:  # believe X-Forwarded-* only from the proxies we were told about
        hops = app.config["PROXY_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # batch mode: SQLite can't ALTER tables directly
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to see that page."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"
    init_security_headers(app)

    from app import models
    from app.admin import bp as admin_bp
    from app.auth import bp as auth_bp
    from app.bookings import bp as bookings_bp
    from app.cli import (bootstrap_admin_command, create_admin_command, reset_db_command,
                         security_scan_command, seed_command)
    from app.flights import bp as flights_bp
    from app.main import bp as main_bp

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(models.User, int(user_id)) if user_id.isdigit() else None

    for blueprint in (main_bp, flights_bp, auth_bp, bookings_bp, admin_bp):
        app.register_blueprint(blueprint)
    for command in (seed_command, reset_db_command, create_admin_command, bootstrap_admin_command,
                    security_scan_command):
        app.cli.add_command(command)

    if app.config.get("AUTO_CREATE_TABLES", True):
        with app.app_context():
            db.create_all()  # adds any missing tables; never touches existing data

    register_template_helpers(app)
    register_error_handlers(app)
    return app


def register_template_helpers(app: Flask) -> None:
    from app.currency import CURRENCIES, current_currency, money, slider_format

    def art_class(slug: str) -> str:
        """"dest-<slug>" when an illustration exists for the city, so its picture is shown."""
        return f"dest-{slug}" if (Path(app.static_folder) / "img" / "destinations" / f"{slug}.svg").is_file() else ""

    app.add_template_global(art_class, "art_class")
    app.add_template_global(money, "money")
    app.add_template_global(current_currency, "current_currency")
    app.add_template_global(slider_format, "slider_format")
    from app.bookings.payment import method_label
    app.add_template_global(method_label, "method_label")
    app.add_template_global(CURRENCIES, "CURRENCIES")

    from app import i18n
    app.add_template_global(i18n.translate, "_")
    app.add_template_global(i18n.translate_months, "translate_months")
    app.add_template_global(i18n.long_date, "long_date")
    app.add_template_global(i18n.current_lang, "current_lang")
    app.add_template_global(i18n.lang_dir, "lang_dir")
    app.add_template_global(i18n.LANGS, "LANGS")
    app.add_template_global(i18n.SHORT, "SHORT")
    app.add_template_filter(i18n.translate, "translate")

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
    @app.errorhandler(400)
    def bad_request(_error):  # includes a missing or expired CSRF token
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def too_many_requests(_error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("errors/500.html"), 500