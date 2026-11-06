"""Rules that keep cancellations deliberate, explained and traceable.

A cancellation needs: the booking's owner, a reason from a fixed list, the account password
(and a two-factor code when it is on). At most three cancellations are allowed in ten minutes
per account, so a stolen session cannot wipe out a whole trip list. Every cancellation is
written to the audit log with the address it came from, and the owner is emailed.
"""
from datetime import timedelta

from sqlalchemy import func, select

from app.extensions import db
from app.models import Booking, utcnow

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
