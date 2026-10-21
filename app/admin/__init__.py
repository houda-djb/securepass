from flask import Blueprint

from app.security import ensure_role

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def require_admin():
    """SR5: every route in this blueprint, now and in the future, needs an admin.
    Doing it here means a new admin page can never be left unprotected by mistake."""
    return ensure_role("admin")


from app.admin import routes  # noqa: E402,F401