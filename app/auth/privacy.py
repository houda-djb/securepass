"""Your data: download everything we hold about you, or delete your account.

The download never contains the password hash, the two-factor secret or recovery codes.
Deleting needs the current password, gives future seats back to the flight, removes your
bookings and names, and keeps only anonymous audit lines (their link to you is cut).
"""
import json
from datetime import datetime, timezone

from flask import Response, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import joinedload

from app.auth import bp
from app.bookings.service import BookingError, cancel_booking
from app.extensions import db, limiter
from app.bookings.holds import release_user_holds
from app.models import AuditLog, Booking, Passenger, RecoveryCode, SeatAssignment, User, UserSession
from app.security import audit


def export_data(user: User) -> dict:
    bookings = db.session.scalars(
        select(Booking).options(joinedload(Booking.flight)).where(Booking.user_id == user.id)
        .order_by(Booking.created_at)).all()
    events = db.session.scalars(
        select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at)).all()
    return {
        "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "account": {"email": user.email, "role": user.role,
                    "created_at_utc": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "two_factor_enabled": bool(user.totp_enabled)},
        "bookings": [{
            "reference": b.reference, "status": b.status, "payment_method": b.payment_method,
            "total_usd": round(b.total_cents / 100, 2),
            "booked_at_utc": b.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "flight": {"number": b.flight.flight_no, "from": b.flight.origin_code,
                       "to": b.flight.destination_code,
                       "departs_at": b.flight.departs_at.strftime("%Y-%m-%d %H:%M")},
            "passengers": [{"name": t.full_name, "seat": t.seat.label if t.seat else None}
                           for t in b.travellers],
        } for b in bookings],
        "security_events": [{"type": e.event_type, "at_utc": e.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                             "ip": e.ip, "detail": e.detail} for e in events],
    }


@bp.route("/account/export")
@login_required
@limiter.limit("10 per hour")
def export_my_data():
    audit("data_exported", current_user)
    body = json.dumps(export_data(current_user), indent=2, ensure_ascii=False)
    return Response(body, mimetype="application/json", headers={
        "Content-Disposition": 'attachment; filename="securepass-my-data.json"',
        "Cache-Control": "no-store"})


def _other_admins(user: User) -> int:
    return db.session.scalar(select(func.count()).select_from(User)
                             .where(User.role == "admin", User.id != user.id))


def delete_account(user: User) -> None:
    """Remove the user and everything that identifies them. Raises BookingError if it can't."""
    bookings = db.session.scalars(
        select(Booking).options(joinedload(Booking.flight)).where(Booking.user_id == user.id)).all()
    for booking in bookings:
        if booking.status == "confirmed" and not booking.flight.has_departed:
            cancel_booking(user.id, booking)  # gives the seats back to the flight
    ids = [b.id for b in bookings]
    if ids:
        db.session.execute(delete(SeatAssignment).where(SeatAssignment.booking_id.in_(ids)))
        db.session.execute(delete(Passenger).where(Passenger.booking_id.in_(ids)))
        db.session.execute(delete(Booking).where(Booking.id.in_(ids)))
    release_user_holds(user.id)  # seats held at checkout go back on sale
    db.session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.session.execute(update(AuditLog).where(AuditLog.user_id == user.id).values(user_id=None))
    db.session.execute(delete(User).where(User.id == user.id))
    db.session.commit()


@bp.route("/account/delete", methods=["POST"])
@login_required
@limiter.limit("5 per hour")
def delete_my_account():
    password = request.form.get("password", "")
    if request.form.get("confirm") != "delete" or not current_user.check_password(password):
        audit("account_delete_refused", current_user)
        flash("Account not deleted: type the word delete and your current password.", "error")
        return redirect(url_for("auth.account") + "#delete")
    if current_user.is_admin and not _other_admins(current_user):
        flash("You are the only administrator. Make someone else an administrator first.", "error")
        return redirect(url_for("auth.account") + "#delete")
    user = db.session.get(User, current_user.id)
    try:
        delete_account(user)
    except BookingError:
        db.session.rollback()
        flash("Your account could not be deleted. Please try again.", "error")
        return redirect(url_for("auth.account") + "#delete")
    audit("account_deleted", None, "an account was deleted by its owner")
    logout_user()
    flash("Your account and its bookings have been deleted.", "info")
    return redirect(url_for("main.index"))


@bp.route("/.well-known/security.txt")
def security_txt():
    """RFC 9116: where to report a vulnerability."""
    repo = current_app.config.get("SECURITY_REPORT_URL",
                                  "https://github.com/houda-djb/securepass/security/advisories/new")
    expires = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1)
    text = (f"Contact: {repo}\nExpires: {expires.strftime('%Y-%m-%dT00:00:00Z')}\n"
            "Preferred-Languages: en, fr, ar\n")
    return Response(text, mimetype="text/plain")
