"""Read-only questions the security dashboard asks the database."""
from datetime import datetime, time, timedelta

from sqlalchemy import func, select

from app.extensions import db
from app.models import AuditLog, Booking, User, utcnow

# FR17: what counts as a "failed login": a wrong password, an attempt on a locked
# account, and the attempt that caused the lock.
FAILED_LOGIN_EVENTS = ("login_failed", "login_blocked", "account_locked")

EVENT_TYPES = (
    "register", "login_success", "login_failed", "login_blocked", "account_locked",
    "account_unlocked", "logout", "access_denied", "booking_created", "booking_cancelled",
    "flight_created", "flight_updated", "flight_deleted",
    "password_changed", "password_reset_requested", "password_reset", "report_exported", "cancel_refused", "cancel_burst_blocked", "cancel_burst_alert", "cancel_ip_blocked", "cancel_site_blocked", "booking_restored", "data_exported", "account_deleted", "account_delete_refused",
)

# Badge colour for each event type on the dashboard.
EVENT_STYLES = {
    "register": "ok", "login_success": "ok", "booking_created": "ok",
    "login_failed": "warn", "login_blocked": "warn",
    "account_locked": "bad", "access_denied": "bad",
}


def dashboard_stats(now: datetime | None = None) -> dict:
    now = now or utcnow()
    since = now - timedelta(hours=24)

    def events_since(types) -> int:
        return db.session.scalar(
            select(func.count(AuditLog.id))
            .where(AuditLog.event_type.in_(types), AuditLog.created_at >= since)
        ) or 0

    return {
        "failed_logins": events_since(FAILED_LOGIN_EVENTS),
        "access_denied": events_since(("access_denied",)),
        "bookings": db.session.scalar(
            select(func.count(Booking.id)).where(Booking.created_at >= since)) or 0,
    }


def locked_users(now: datetime | None = None):
    """FR18: accounts that are locked right now."""
    now = now or utcnow()
    return db.session.scalars(
        select(User).where(User.locked_until.is_not(None), User.locked_until > now)
        .order_by(User.locked_until)
    ).all()


def recent_events(event_type: str | None = None, limit: int = 25):
    """FR19: the newest audit events, optionally of one type, with the user's email."""
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    if event_type in EVENT_TYPES:  # anything else is ignored, never put into a query
        stmt = stmt.where(AuditLog.event_type == event_type)
    return db.session.execute(stmt).all()


def bookings_per_day(days: int = 14, today=None) -> list[tuple]:
    """FR20: how many bookings were made on each of the last N days (UTC), zeros included."""
    today = today or utcnow().date()
    start = today - timedelta(days=days - 1)
    rows = db.session.execute(
        select(func.date(Booking.created_at), func.count(Booking.id))
        .where(Booking.created_at >= datetime.combine(start, time.min))
        .group_by(func.date(Booking.created_at))
    ).all()
    counts = {str(day): total for day, total in rows}
    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        result.append((day, counts.get(day.isoformat(), 0)))
    return result


def build_chart(points, width: int = 560, height: int = 190, top: int = 24, bottom: int = 28) -> dict:
    """Turn (day, count) pairs into SVG bar coordinates.
    Drawing the chart on the server means no JavaScript library and nothing extra to trust."""
    peak = max((count for _, count in points), default=0) or 1
    slot = width / len(points)
    bar_width = slot * 0.62
    plot_height = height - top - bottom
    bars = []
    for index, (day, count) in enumerate(points):
        bar_height = round(plot_height * count / peak, 1)
        bars.append({
            "x": round(index * slot + (slot - bar_width) / 2, 1),
            "y": round(top + plot_height - bar_height, 1),
            "w": round(bar_width, 1),
            "h": bar_height,
            "cx": round(index * slot + slot / 2, 1),
            "count": count,
            "label": day.strftime("%d/%m"),
            "show_label": index % 2 == 0,
        })
    return {"width": width, "height": height, "bars": bars,
            "baseline": top + plot_height, "label_y": height - 8, "peak": peak}