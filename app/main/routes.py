from datetime import date, datetime

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

from app.currency import CURRENCIES
from app.extensions import db, limiter
from app.main import bp
from app.i18n import LANGS
from app.main.seasons import (MONTH_NAMES, SEASON_ORDER, SEASONS, STYLES, best_time_text, clean_month,
                              clean_season, fits)
from app.models import Airport, Booking, Country, Flight
from app.security import is_safe_next
from app.security_headers import talisman

HOME_AIRPORT = "ALG"                    # prices on the site are "from Alger"
TOP_TRIPS = ("IST", "CDG", "DXB", "MAD", "TUN", "KUL", "YUL", "CAI")


def lowest_fares(origin: str | None = None) -> dict[str, int]:
    """The cheapest upcoming fare (in cents) to each airport that still has seats.

    One grouped query for the whole page, so showing "From ..." costs no extra round trips.
    With `origin`, only flights leaving from that airport count.
    Flight times are plain local times in this demo, so compare with local time.
    """
    stmt = (select(Flight.destination_code, func.min(Flight.price_cents))
            .where(Flight.departs_at >= datetime.now(), Flight.seats_available > 0)
            .group_by(Flight.destination_code))
    if origin:
        stmt = stmt.where(Flight.origin_code == origin)
    return {code: cents for code, cents in db.session.execute(stmt).all()}


def country_fares(countries: list[Country], airports: list[Airport]) -> dict[str, int]:
    """The cheapest fare to each country, taking Alger as the starting point when possible."""
    home = lowest_fares(HOME_AIRPORT)
    anywhere = lowest_fares()
    by_country: dict[str, list[str]] = {}
    for a in airports:
        by_country.setdefault(a.country, []).append(a.code)
    result = {}
    for c in countries:
        codes = by_country.get(c.name, [])
        prices = [home[code] for code in codes if code in home] or [anywhere[code] for code in codes if code in anywhere]
        if prices:
            result[c.slug] = min(prices)
    return result


def _country_cards(countries: list[Country]) -> tuple[list[Airport], dict[str, int], dict[str, str]]:
    airports = db.session.scalars(select(Airport).order_by(Airport.city)).all()
    return airports, country_fares(countries, airports), {c.slug: best_time_text(c.months) for c in countries}


def dashboard_for(user):
    """The signed-in visitor's next trip, for the home page panel. None for anonymous visitors."""
    if not getattr(user, "is_authenticated", False):
        return None
    now = datetime.now()  # flight times are plain local times in this demo
    upcoming = db.session.scalars(
        select(Booking).join(Booking.flight).options(joinedload(Booking.flight))
        .where(Booking.user_id == user.id, Booking.status == "confirmed", Flight.departs_at > now)
        .order_by(Flight.departs_at).limit(1)).first()
    total = db.session.scalar(select(func.count()).select_from(Booking)
                              .where(Booking.user_id == user.id, Booking.status == "confirmed"))
    return {"next": upcoming, "total": total or 0}


@bp.route("/")
def index():
    today = date.today()
    airports = db.session.scalars(select(Airport).order_by(Airport.city)).all()
    season = clean_season(request.args.get("season"), today)
    months = SEASONS[season]

    countries = db.session.scalars(select(Country).order_by(Country.name)).all()
    in_season = sorted((c for c in countries if fits(c, months)), key=lambda c: (-fits(c, months), c.name))[:5]
    fares_by_country = country_fares(countries, airports)

    home_fares = lowest_fares(HOME_AIRPORT)
    by_code = {a.code: a for a in airports}
    top_trips = [by_code[code] for code in TOP_TRIPS if code in by_code and code in home_fares][:4]
    return render_template(
        "index.html", airports=airports, values={"origin": HOME_AIRPORT}, errors={},
        season=season, seasons=SEASON_ORDER, in_season=in_season, country_fares=fares_by_country,
        best_time={c.slug: best_time_text(c.months) for c in in_season},
        top_trips=top_trips, home_fares=home_fares, home=by_code.get(HOME_AIRPORT),
        country_count=len(countries), city_count=len(airports), dashboard=dashboard_for(current_user))


@bp.route("/countries")
def countries():
    rows = db.session.scalars(select(Country).order_by(Country.name)).all()
    airports, fares, best = _country_cards(rows)
    cities = {}
    for a in airports:
        cities.setdefault(a.country, []).append(a)
    return render_template("countries.html", countries=rows, fares=fares, best=best, cities=cities)


@bp.route("/countries/<slug>")
def country(slug: str):
    row = db.session.get(Country, slug[:40])
    if row is None:
        abort(404)
    airports = db.session.scalars(select(Airport).where(Airport.country == row.name).order_by(Airport.city)).all()
    home = lowest_fares(HOME_AIRPORT)
    anywhere = lowest_fares()
    fares = {a.code: home.get(a.code, anywhere.get(a.code)) for a in airports}
    return render_template("country.html", country=row, airports=airports, fares=fares,
                           best=best_time_text(row.months), months=[MONTH_NAMES[m - 1] for m in row.months],
                           styles=[STYLES.get(x, x) for x in row.style_list])


@bp.route("/plan")
def plan():
    """Pick a month (and optionally a trip style) and see where it is a good time to go."""
    today = date.today()
    month = clean_month(request.args.get("month")) or today.month
    style = request.args.get("style", "")
    style = style if style in STYLES else ""
    rows = db.session.scalars(select(Country).order_by(Country.name)).all()
    matches = [c for c in rows if month in c.months and (not style or style in c.style_list)]
    airports, fares, best = _country_cards(matches)
    return render_template("plan.html", month=month, month_name=MONTH_NAMES[month - 1], style=style,
                           months=MONTH_NAMES, styles=STYLES, matches=matches, fares=fares, best=best)


@bp.route("/currency", methods=["POST"])
@limiter.limit("60 per hour")
def choose_currency():
    """Remember how the visitor wants prices shown. Only a known currency code is accepted."""
    code = request.form.get("currency", "")
    if code in CURRENCIES:
        session["currency"] = code
    target = request.form.get("next", "")
    return redirect(target if is_safe_next(target) else url_for("main.index"))


@bp.route("/language", methods=["POST"])
@limiter.limit("60 per hour")
def choose_language():
    """Remember the visitor's language. Only the three known codes are accepted."""
    code = request.form.get("lang", "")
    if code in LANGS:
        session["lang"] = code
    target = request.form.get("next", "")
    return redirect(target if is_safe_next(target) else url_for("main.index"))


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
