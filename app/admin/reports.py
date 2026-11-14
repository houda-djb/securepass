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


SUSPICIOUS_COUNT = 3  # this many cancellations by one account in a day is flagged


def cancellation_rows(limit: int = 200) -> tuple[list[dict], int]:
    """Latest cancellations with who, why and from where, flagging accounts that cancel a lot."""
    rows = db.session.scalars(
        select(Booking).options(joinedload(Booking.flight), joinedload(Booking.user))
        .where(Booking.status == "cancelled").order_by(Booking.cancelled_at.desc()).limit(limit)).all()
    day_ago = utcnow() - timedelta(days=1)
    per_user: dict[int, int] = {}
    for b in rows:
        if b.cancelled_at and b.cancelled_at >= day_ago:
            per_user[b.user_id] = per_user.get(b.user_id, 0) + 1
    result = [{"booking": b, "flagged": per_user.get(b.user_id, 0) >= SUSPICIOUS_COUNT,
               "unexplained": not b.cancel_reason, "restorable": not b.flight.has_departed} for b in rows]
    return result, sum(1 for r in result if r["flagged"] or r["unexplained"])


def shield_status() -> dict:
    """What the cancellation shield did in the last 24 hours, and the limits it applies."""
    from app.bookings.cancellation import BURST_LIMIT, ip_limit, site_limit
    from app.models import AuditLog
    since = utcnow() - timedelta(days=1)

    def count(event):
        return db.session.scalar(select(func.count()).select_from(AuditLog)
                                 .where(AuditLog.event_type == event, AuditLog.created_at >= since)) or 0
    return {"account_blocked": count("cancel_burst_blocked"), "address_blocked": count("cancel_ip_blocked"),
            "site_blocked": count("cancel_site_blocked"), "restored": count("booking_restored"),
            "limits": {"account": BURST_LIMIT, "address": ip_limit(), "site": site_limit()}}
