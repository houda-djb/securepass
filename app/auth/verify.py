"""Confirming an email address (Phase 32).

The link carries a signed, time-limited token holding the user id and the address it was sent to,
so it stops working if the address changes. Nothing is stored and the token is never logged.
"""
from flask import current_app, url_for
from itsdangerous import BadData, URLSafeTimedSerializer

from app.extensions import db
from app.models import User

SALT = "email-verify"
VERIFY_DAYS = 3


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def make_token(user: User) -> str:
    return _serializer().dumps({"id": user.id, "email": user.email})


def user_for_token(token: str) -> User | None:
    try:
        data = _serializer().loads(token, max_age=VERIFY_DAYS * 86400)
        user = db.session.get(User, int(data["id"]))
    except (BadData, KeyError, TypeError, ValueError):
        return None
    if user is None or user.email != data.get("email"):
        return None
    return user


def send_verification(user: User) -> None:
    from app.bookings.notify import _deliver  # imported here: the bookings package imports this module
    link = url_for("auth.verify_email", token=make_token(user), _external=True)
    _deliver(user.email, "Confirm your SecurePass email",
             "Welcome to SecurePass.\n\nConfirm your email address with this link "
             f"(valid for {VERIFY_DAYS} days):\n{link}\n\n"
             "If you did not create this account, ignore this message.\n")


def must_verify(user: User) -> bool:
    """True when this site requires a confirmed email and the user has not confirmed theirs."""
    return bool(current_app.config.get("REQUIRE_EMAIL_VERIFICATION")) and not user.email_verified
