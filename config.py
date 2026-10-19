"""Application configuration. Secrets come from environment variables (SR11)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    # SR11: no hard-coded secret. Production must set SECRET_KEY in the environment.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # SR4: all database access goes through SQLAlchemy (parameterized queries).
    # A relative sqlite path is created inside the instance/ folder (git-ignored).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///securepass.db")

    # SR7: rate limiting for sensitive endpoints (in-memory is fine for one server).
    RATELIMIT_STORAGE_URI = "memory://"

    # FR3: account lockout policy.
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    # SR8: hardened session cookies (Secure is switched on in ProductionConfig).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)


class DevelopmentConfig(Config):
    DEBUG = False  # keep the debugger off even in dev; use `flask run --debug` deliberately
    # Dev-only convenience so the app starts without a .env file.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-not-for-production"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Switched off so most tests stay simple. Dedicated tests turn them back on.
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}