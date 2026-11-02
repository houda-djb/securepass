from datetime import datetime

from flask import current_app, jsonify, render_template
from sqlalchemy import func, select, text

from app.extensions import db, limiter
from app.main import bp
from app.models import Airport, Flight
from app.security_headers import talisman


def lowest_fares() -> dict[str, int]:
    """The cheapest upcoming fare (in cents) to each airport that still has seats.

    One grouped query for the whole homepage, so showing "From $95" costs no extra round trips.
    Flight times are plain local times in this demo, so compare with local time.
    """
    rows = db.session.execute(
        select(Flight.destination_code, func.min(Flight.price_cents))
        .where(Flight.departs_at >= datetime.now(), Flight.seats_available > 0)
        .group_by(Flight.destination_code)
    ).all()
    return {code: cents for code, cents in rows}


@bp.route("/")
def index():
    airports = db.session.scalars(select(Airport).order_by(Airport.city)).all()
    featured = db.session.scalars(
        select(Airport).where(Airport.featured_rank.is_not(None)).order_by(Airport.featured_rank)
    ).all()
    from_prices = lowest_fares()
    # Everything that is not featured, cheapest first, for the "More places to go" strip.
    more = sorted(
        (a for a in airports if a.featured_rank is None and a.code in from_prices),
        key=lambda a: (from_prices[a.code], a.city),
    )
    return render_template("index.html", featured=featured, airports=airports, values={}, errors={},
                           from_prices=from_prices, more=more)


@bp.route("/healthz")
@limiter.exempt
@talisman(force_https=False)   # the hosting platform checks this over plain http inside its network
def healthz():
    """Used by the hosting platform to see whether the app and its database are alive.

    It says nothing about versions, settings or what went wrong: only "ok" or "unavailable".
    """
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # any database problem means "not healthy"; details stay in the logs
        db.session.rollback()
        current_app.logger.exception("Health check: the database did not answer.")
        response, status = jsonify(status="unavailable"), 503
    else:
        response, status = jsonify(status="ok"), 200
    response.headers["Cache-Control"] = "no-store"
    return response, status
