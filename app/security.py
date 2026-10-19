"""Shared security helpers: audit log, role checks and safe redirects."""
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def audit(event_type: str, user=None, detail: str = "") -> None:
    """SR13: record a security event. Never pass passwords or tokens in `detail`."""
    db.session.add(AuditLog(
        user_id=user.id if user is not None else None,
        event_type=event_type,
        ip=(request.remote_addr or "")[:45],
        detail=detail[:200],
    ))
    db.session.commit()


def role_required(*roles: str):
    """SR5: the server decides who may open a page. Hiding a link is not enough."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                audit("access_denied", current_user, request.path)
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def is_safe_next(target: str | None) -> bool:
    """Only allow redirects to a path on this site (prevents open-redirect attacks)."""
    if not target:
        return False
    parts = urlparse(target)
    return (
        not parts.scheme
        and not parts.netloc
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
    )