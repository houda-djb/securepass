"""Sales reports for the admin: numbers for the page and a CSV export.

Money is kept in US dollar cents, as everywhere else, and shown with the site's display currency.
Every cell written to the CSV is checked so a spreadsheet can never run it as a formula.
"""
import csv
import io
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.bookings.payment import method_label
from app.extensions import db
from app.models import Booking, Flight, User, utcnow

RANGES = {"7": 7, "30": 30, "90": 90, "365": 365}
DEFAULT_RANGE = "30"
CSV_HEADER = ["reference", "booked_at_utc", "status", "payment_method", "route", "flight_no",
              "departs_at_utc", "passengers", "total_usd", "customer_email"]
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def clean_range(raw: str | None) -> str:
    return raw if raw in RANGES else DEFAULT_RANGE


def safe_cell(value) -> str:
    """Text for a CSV cell. A leading = + - @ would be run as a formula by Excel, so we defuse it."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def since(range_key: str):
    return utcnow() - timedelta(days=RANGES[range_key])


def summary(range_key: str) -> dict:
    start = since(range_key)
    base = select(Booking).where(Booking.created_at >= start)
    confirmed = base.where(Booking.status == "confirmed").subquery()
    row = db.session.execute(
        select(func.count(), func.coalesce(func.sum(confirmed.c.total_cents), 0),
               func.coalesce(func.sum(confirmed.c.passengers), 0)).select_from(confirmed)).one()
    cancelled = db.session.scalar(
        select(func.count()).select_from(Booking)
        .where(Booking.created_at >= start, Booking.status == "cancelled"))
    new_users = db.session.scalar(select(func.count()).select_from(User).where(User.created_at >= start))
    return {"bookings": row[0], "revenue_cents": int(row[1]), "passengers": int(row[2]),
            "cancelled": cancelled, "new_users": new_users,
            "average_cents": int(row[1] // row[0]) if row[0] else 0}


def by_payment_method(range_key: str) -> list[dict]:
    rows = db.session.execute(
        select(Booking.payment_method, func.count(), func.coalesce(func.sum(Booking.total_cents), 0))
        .where(Booking.created_at >= since(range_key), Booking.status == "confirmed")
        .group_by(Booking.payment_method).order_by(func.count().desc())).all()
    return [{"label": method_label(m), "count": c, "cents": int(t)} for m, c, t in rows]


def top_routes(range_key: str, limit: int = 8) -> list[dict]:
    rows = db.session.execute(
        select(Flight.origin_code, Flight.destination_code, func.count(Booking.id),
               func.coalesce(func.sum(Booking.total_cents), 0))
        .join(Booking, Booking.flight_id == Flight.id)
        .where(Booking.created_at >= since(range_key), Booking.status == "confirmed")
        .group_by(Flight.origin_code, Flight.destination_code)
        .order_by(func.count(Booking.id).desc(), Flight.origin_code, Flight.destination_code)
        .limit(limit)).all()
    return [{"route": f"{o} to {d}", "count": c, "cents": int(t)} for o, d, c, t in rows]


def bookings_csv(range_key: str) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    rows = db.session.scalars(
        select(Booking).options(joinedload(Booking.flight), joinedload(Booking.user))
        .where(Booking.created_at >= since(range_key)).order_by(Booking.created_at.desc())).all()
    for b in rows:
        writer.writerow([safe_cell(x) for x in (
            b.reference, b.created_at.strftime("%Y-%m-%d %H:%M"), b.status, b.payment_method,
            f"{b.flight.origin_code}-{b.flight.destination_code}", b.flight.flight_no,
            b.flight.departs_at.strftime("%Y-%m-%d %H:%M"), b.passengers,
            f"{b.total_cents / 100:.2f}", b.user.email)])
    return out.getvalue()
