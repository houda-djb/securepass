"""Rules that keep cancellations deliberate, explained and traceable.

A cancellation needs: the booking's owner, a reason from a fixed list, the account password
(and a two-factor code when it is on). At most three cancellations are allowed in ten minutes
per account, so a stolen session cannot wipe out a whole trip list. Every cancellation is
written to the audit log with the address it came from, and the owner is emailed.
"""
from datetime import timedelta

from flask import current_app
from sqlalchemy import func, select

from app.extensions import db
from app.models import AuditLog, Booking, utcnow

REASONS = {
    "plans": "My plans changed",
    "cheaper": "I found a cheaper flight",
    "dates": "I chose the wrong dates",
    "names": "A passenger name is wrong",
    "travel": "A travel or visa problem",
    "other": "Another reason",
}
BURST_LIMIT = 3
BURST_WINDOW = timedelta(minutes=10)

# Phase 30, the cancellation shield. An attacker with many stolen passwords stays under the
# per-account limit, so the whole network address and the whole site are limited as well.
IP_LIMIT, IP_WINDOW = 5, timedelta(hours=1)        # cancellations from one address per hour
SITE_LIMIT, SITE_WINDOW = 15, timedelta(minutes=10)  # cancellations on the whole site


def ip_limit() -> int:
    return current_app.config.get("CANCEL_IP_LIMIT", IP_LIMIT)


def site_limit() -> int:
    return current_app.config.get("CANCEL_SITE_LIMIT", SITE_LIMIT)


def _done(window: timedelta, ip: str | None = None) -> int:
    """Cancellations made in the window, counted from the audit log. An undo does not lower the
    count, so an attacker cannot keep going just because victims restore their bookings."""
    query = select(func.count()).select_from(AuditLog).where(
        AuditLog.event_type == "booking_cancelled", AuditLog.created_at >= utcnow() - window)
    if ip is not None:
        query = query.where(AuditLog.ip == ip)
    return db.session.scalar(query) or 0


def too_many_from_address(ip: str) -> bool:
    return bool(ip) and _done(IP_WINDOW, ip) >= ip_limit()


def site_paused() -> bool:
    return _done(SITE_WINDOW) >= site_limit()


def seen_recently(event_type: str, window: timedelta) -> bool:
    """True if this kind of alert was already raised in the window (so the admin is mailed once)."""
    return bool(db.session.scalar(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.event_type == event_type, AuditLog.created_at >= utcnow() - window)))


def clean_reason(raw) -> str | None:
    return raw if isinstance(raw, str) and raw in REASONS else None


def reason_label(key) -> str:
    return REASONS.get(key, "No reason recorded")


def recent_cancellations(user_id: int, window: timedelta = BURST_WINDOW) -> int:
    return db.session.scalar(
        select(func.count()).select_from(Booking)
        .where(Booking.user_id == user_id, Booking.status == "cancelled",
               Booking.cancelled_at >= utcnow() - window)) or 0


def too_many_recent(user_id: int) -> bool:
    return recent_cancellations(user_id) >= BURST_LIMIT
