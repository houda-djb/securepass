from datetime import datetime

from flask import render_template
from sqlalchemy import func, select

from app.extensions import db
from app.main import bp
from app.models import Airport, Flight


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
