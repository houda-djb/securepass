"""Password reset links.

A link carries a signed, time-limited token. It holds the user id and a short fingerprint of the
current password hash, so it stops working as soon as the password changes (one use only).
Nothing is stored in the database and the token is never written to the audit log.
"""
import hashlib
import hmac
import logging
import os
import smtplib
from email.message import EmailMessage

from flask import current_app, url_for
from itsdangerous import BadData, URLSafeTimedSerializer

from app.extensions import db
from app.models import User

RESET_MINUTES = 30
SALT = "password-reset"
log = logging.getLogger(__name__)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def _fingerprint(user: User) -> str:
    key = current_app.config["SECRET_KEY"]
    key = key.encode() if isinstance(key, str) else key
    return hmac.new(key, user.password_hash.encode(), hashlib.sha256).hexdigest()[:16]


def make_token(user: User) -> str:
    return _serializer().dumps({"id": user.id, "fp": _fingerprint(user)})


def user_for_token(token: str) -> User | None:
    """The user a valid, unexpired, unused token belongs to, otherwise None."""
    try:
        data = _serializer().loads(token, max_age=RESET_MINUTES * 60)
        user = db.session.get(User, int(data["id"]))
    except (BadData, KeyError, TypeError, ValueError):
        return None
    if user is None or not hmac.compare_digest(data.get("fp", ""), _fingerprint(user)):
        return None
    return user


def reset_link(user: User) -> str:
    # PUBLIC_URL (for example https://securepass.example) stops a forged Host header from
    # putting an attacker's address into the email.
    token = make_token(user)
    base = os.environ.get("PUBLIC_URL", "").rstrip("/")
    if base:
        return f"{base}{url_for('auth.reset_password', token=token)}"
    return url_for("auth.reset_password", token=token, _external=True)


def send_reset_email(user: User) -> None:
    link = reset_link(user)
    body = (f"Someone asked to reset the password of your SecurePass account.\n\n"
            f"Open this link within {RESET_MINUTES} minutes to choose a new password:\n{link}\n\n"
            "If this was not you, ignore this email. Your password stays the same.\n")

    if current_app.testing:
        current_app.extensions.setdefault("outbox", []).append(
            {"to": user.email, "body": body, "link": link})
        return

    host = os.environ.get("SMTP_HOST")
    if not host:
        if current_app.config.get("FORCE_HTTPS"):
            log.warning("Password reset requested but SMTP_HOST is not set: no email was sent.")
        else:  # development only: show the link in the console instead of sending mail
            log.warning("DEV MODE, reset link for %s: %s", user.email, link)
        return

    message = EmailMessage()
    message["Subject"] = "Reset your SecurePass password"
    message["From"] = os.environ.get("MAIL_FROM", "no-reply@securepass.local")
    message["To"] = user.email
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            if os.environ.get("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        log.exception("Could not send the password reset email.")  # never tell the visitor
