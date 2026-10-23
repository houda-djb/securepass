"""Application configuration. Secrets come from environment variables (SR11)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a whole number, not {raw!r}.") from None
    if not 0 <= value <= maximum:
        raise RuntimeError(f"{name} must be between 0 and {maximum}.")
    return value


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

    # SR9: redirect http to https and send HSTS (only switched on in ProductionConfig).
    FORCE_HTTPS = False

    # Largest request body we accept. Every form here is tiny, so a big body is an attack
    # or a mistake, never a real visitor.
    MAX_CONTENT_LENGTH = 100 * 1024

    # How many reverse proxies sit in front of the app (0 = none, the safe default).
    # Only then are X-Forwarded-For and X-Forwarded-Proto believed; otherwise anyone could
    # fake their IP address and dodge the login rate limit.
    PROXY_HOPS = _env_int("PROXY_HOPS", 0, maximum=5)


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
    DEBUG = False
    FORCE_HTTPS = True
    SESSION_COOKIE_SECURE = True
    # "__Host-" tells the browser to accept this cookie only if it is Secure, has Path=/
    # and has no Domain, so no other site or subdomain can overwrite it.
    SESSION_COOKIE_NAME = "__Host-session"
    PREFERRED_URL_SCHEME = "https"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}