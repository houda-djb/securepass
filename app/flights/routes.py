from datetime import datetime, time, timedelta

from flask import abort, render_template, request
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.flights import bp
from app.flights.validation import validate_search
from app.models import Airport, Flight

FORM_FIELDS = ("origin", "destination", "departure", "return", "passengers")


def _flights_on_day(origin: str, destination: str, day, passengers: int):
    start = datetime.combine(day, time.min)
    stmt = (
        select(Flight)
        .options(joinedload(Flight.origin), joinedload(Flight.destination))
        .where(
            Flight.origin_code == origin,
            Flight.destination_code == destination,
            Flight.departs_at >= start,
            Flight.departs_at < start + timedelta(days=1),
            Flight.seats_available >= passengers,
        )
        .order_by(Flight.departs_at)
    )
    return db.session.scalars(stmt).all()


@bp.route("/flights")
def search():
    airports = db.session.scalars(select(Airport).order_by(Airport.city)).all()
    known_codes = {airport.code for airport in airports}

    # Values shown back in the form. Trimmed to a short length; Jinja escapes them (SR10).
    values = {field: request.args.get(field, "")[:20] for field in FORM_FIELDS}

    # A real search sends the button's name=search. Links such as "View flights to Tokyo"
    # only pre-fill the form, so they don't show validation errors.
    submitted = "search" in request.args

    query, errors = (validate_search(request.args) if submitted else (None, {}))
    outbound = returning = None

    if query:
        for field, code in (("origin", query.origin), ("destination", query.destination)):
            if code not in known_codes:
                errors[field] = "We don't fly to or from that airport yet."
    if query and not errors:
        outbound = _flights_on_day(query.origin, query.destination, query.departure, query.passengers)
        if query.return_date:
            returning = _flights_on_day(query.destination, query.origin, query.return_date, query.passengers)

    status = 400 if errors else 200
    return render_template(
        "flights/search.html", airports=airports, values=values, errors=errors,
        submitted=submitted, query=query, outbound=outbound, returning=returning,
    ), status


@bp.route("/flights/<int:flight_id>")
def detail(flight_id: int):
    if flight_id > 2_147_483_647:  # larger than any real id; avoids a database overflow
        abort(404)
    flight = db.get_or_404(Flight, flight_id)
    return render_template("flights/detail.html", flight=flight)