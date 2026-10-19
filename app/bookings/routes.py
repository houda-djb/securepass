from flask import render_template
from flask_login import login_required

from app.bookings import bp


@bp.route("/")
@login_required
def index():
    # Phase 4 replaces this placeholder with the user's real bookings.
    return render_template("coming_soon.html", title="My bookings", phase="Phase 4")