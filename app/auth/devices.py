"""The list of signed-in devices (Phase 32).

Each login gets a random id kept in the signed session cookie and a row in `user_sessions`.
Every request checks the row, so revoking it logs that one device out at once.
"""
import secrets
from datetime import timedelta

from flask import flash, redirect, request, session, url_for
from flask_login import current_user, logout_user
from sqlalchemy import select, update

from app.extensions import db
from app.models import User, UserSession, utcnow

TOUCH_EVERY = timedelta(minutes=5)   # how often "last seen" is refreshed
SHOWN = 10


def label(user_agent: str) -> str:
    ua = user_agent or ""
    browser = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                           ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua), "Browser")
    system = next((name for key, name in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"),
                                          ("iPad", "iPad"), ("Mac OS", "macOS"), ("Linux", "Linux")) if key in ua),
                  "unknown system")
    return f"{browser} on {system}"


def register_device(user: User) -> None:
    sid = secrets.token_urlsafe(24)
    db.session.add(UserSession(user_id=user.id, sid=sid, ip=(request.remote_addr or "")[:64],
                               user_agent=(request.headers.get("User-Agent") or "")[:200]))
    db.session.commit()
    session["sid"] = sid


def revoke_all(user_id: int, keep_sid: str | None = None) -> None:
    query = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if keep_sid:
        query = query.where(UserSession.sid != keep_sid)
    db.session.execute(query.values(revoked_at=utcnow()))
    db.session.commit()


def active_devices(user: User):
    return db.session.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc(), UserSession.id.desc()).limit(SHOWN)).all()


def _sign_out(message: str):
    logout_user()
    session.clear()
    flash(message, "info")
    return redirect(url_for("auth.login"))


def register(app) -> None:
    @app.before_request
    def check_device():
        if request.endpoint in (None, "static") or not current_user.is_authenticated:
            return None
        sid = session.get("sid")
        row = None
        if sid:
            row = db.session.scalar(select(UserSession).where(UserSession.sid == sid,
                                                              UserSession.user_id == current_user.id))
            if row is None:
                return _sign_out("Please log in again.")
        if row is None:  # a session from before this feature: give it a row now
            register_device(current_user._get_current_object())
            return None
        if row.revoked_at is not None:
            return _sign_out("This device was signed out from another device.")
        now = utcnow()
        if now - row.last_seen_at > TOUCH_EVERY:
            row.last_seen_at = now
            db.session.commit()
        return None
