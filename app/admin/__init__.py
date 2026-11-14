from flask import Blueprint, current_app, flash, redirect, url_for
from flask_login import current_user

from app.security import ensure_role

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def require_admin():
    """SR5: every route in this blueprint, now and in the future, needs an admin.
    Doing it here means a new admin page can never be left unprotected by mistake."""
    denied = ensure_role("admin")
    if denied is not None:
        return denied
    if current_app.config.get("REQUIRE_ADMIN_2FA") and not current_user.totp_enabled:
        flash("Administrators must turn on two-factor login before using the admin area.", "info")
        return redirect(url_for("auth.two_factor_setup"))
    return None


from app.admin import routes  # noqa: E402,F401