import os
from pathlib import Path

from flask import Flask, render_template, url_for

from app.extensions import db
from config import CONFIGS


def create_app(config_name: str | None = None) -> Flask:
    """Application factory: tests can build an isolated app with config_name='testing'."""
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    config_class = CONFIGS.get(config_name, CONFIGS["development"])

    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Add it to your environment or .env file.")

    db.init_app(app)

    from app import models  # noqa: F401  (registers the tables)
    from app.cli import seed_command
    from app.flights import bp as flights_bp
    from app.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(flights_bp)
    app.cli.add_command(seed_command)

    with app.app_context():
        db.create_all()

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
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("errors/500.html"), 500