from flask import render_template

from app.admin import bp
from app.security import role_required


@bp.route("/")
@role_required("admin")
def index():
    # Phase 5 replaces this placeholder with the security dashboard.
    return render_template("coming_soon.html", title="Admin dashboard", phase="Phase 5")