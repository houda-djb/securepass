import re

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.bookings import bp
from app.bookings.barcode import bars, total_width
from app.bookings.forms import BookingForm
from app.bookings.holds import HOLD_MINUTES, active_hold, place_hold, seconds_left
from app.bookings.cancellation import (BURST_LIMIT, BURST_WINDOW, IP_WINDOW, REASONS, SITE_WINDOW, clean_reason,
                                       ip_limit, recent_cancellations, seen_recently, site_limit, site_paused,
                                       too_many_from_address, too_many_recent)
from app.bookings.notify import send_admin_alert, send_cancellation_notice, send_confirmation
from app.bookings.payment import METHODS, clean_method
from app.bookings.passengers import read_passengers, submitted_values
from app.bookings.seats import (CAPACITY, EXIT_ROWS, LEFT, RIGHT, ROWS, choose_seats, is_valid_label,
                                seat_problem, taken_seats)
from app.bookings.service import (MAX_PASSENGERS, BookingError, booking_problem, cancel_booking,
                                  create_booking, restore_booking)
from app.auth.routes import _second_factor_ok
from app.extensions import db, limiter
from app.models import Booking, Flight, Passenger
from app.security import audit

REFERENCE_PATTERN = re.compile(r"^[A-Z0-9]{8}$")
MAX_ID = 2_147_483_647


def _clamp_passengers(raw) -> int:
    raw = str(raw if raw is not None else "1")
    if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= MAX_PASSENGERS:
        return int(raw)
    return 1


def _with_flight_details():
    return joinedload(Booking.flight).options(joinedload(Flight.origin), joinedload(Flight.destination))


def _own_booking_or_404(reference: str) -> Booking:
    """SR6: look bookings up by user AND reference. Someone else's booking looks like a missing one."""
    if not REFERENCE_PATTERN.match(reference):
        abort(404)
    booking = db.session.scalar(
        select(Booking).options(_with_flight_details(),
                                selectinload(Booking.travellers).selectinload(Passenger.seat))
        .where(Booking.reference == reference, Booking.user_id == current_user.id)
    )
    if booking is None:
        # Same 404 for "doesn't exist" and "not yours", but we keep a record of the attempt.
        if db.session.scalar(select(Booking.id).where(Booking.reference == reference)) is not None:
            audit("access_denied", current_user, f"booking {reference}")
        abort(404)
    return booking


@bp.route("/")
@login_required
def index():
    bookings = db.session.scalars(
        select(Booking).join(Booking.flight).options(_with_flight_details())
        .where(Booking.user_id == current_user.id)
        .order_by(Flight.departs_at.desc())
    ).all()
    return render_template("bookings/index.html", bookings=bookings)


@bp.route("/new/<int:flight_id>", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per 10 minutes", methods=["GET"], key_func=lambda: f"hold-{current_user.get_id()}")
def new(flight_id: int):
    if flight_id > MAX_ID:
        abort(404)
    flight = db.get_or_404(Flight, flight_id)

    status, message = 200, None
    name_values, name_errors = {}, {}
    form = BookingForm()
    if request.method == "POST":
        if form.validate_on_submit():
            passengers = form.passengers.data
            names, name_errors = read_passengers(request.form, passengers)
            name_values = submitted_values(request.form, passengers)
            if name_errors:
                status = 400
            else:
                try:
                    method = clean_method(request.form.get("payment_method"))
                    booking = create_booking(current_user.id, flight.id, passengers, names, method)
                except BookingError as error:
                    message, status = str(error), 400
                else:
                    audit("booking_created", current_user,
                          f"{booking.reference} {flight.flight_no} x{passengers}")
                    send_confirmation(booking)
                    flash("Booking confirmed. Your reference is " + booking.reference + ".", "success")
                    return redirect(url_for("bookings.detail", reference=booking.reference))
        else:
            message, status = f"Choose between 1 and {MAX_PASSENGERS} passengers.", 400
        passengers = _clamp_passengers(form.passengers.data)
    else:
        passengers = _clamp_passengers(request.args.get("passengers"))

    form = BookingForm(formdata=None, passengers=passengers)  # fresh form with a fresh token
    db.session.refresh(flight)
    hold = active_hold(current_user.id, flight.id, passengers)
    if hold is None and not message and request.method == "GET":
        try:
            hold = place_hold(current_user.id, flight, passengers)  # keep the seats for 15 minutes
        except BookingError as error:
            message = str(error)
    problem = message or (None if hold else booking_problem(flight, passengers))
    return render_template("bookings/checkout.html", flight=flight, form=form,
                           passengers=passengers, problem=problem,
                           hold_left=seconds_left(hold), hold_minutes=HOLD_MINUTES,
                           name_values=name_values, name_errors=name_errors, methods=METHODS,
                           chosen_method=clean_method(request.form.get("payment_method")),
                           total_cents=flight.price_cents * passengers), status


@bp.route("/<reference>")
@login_required
def detail(reference: str):
    return render_template("bookings/detail.html", booking=_own_booking_or_404(reference))


@bp.route("/<reference>/ticket")
@login_required
def ticket(reference: str):
    """A printable e-ticket. Only the owner can open it, and a cancelled booking has none."""
    booking = _own_booking_or_404(reference)
    if booking.is_cancelled:
        abort(404)
    items = bars(booking.reference)
    return render_template("bookings/ticket.html", booking=booking, bars=items, bar_width=total_width(items))


def _alert(event: str, window, user, detail: str, text: str) -> None:
    """Log a blocked cancellation and, the first time in the window, email the administrators."""
    first = not seen_recently(event, window)
    audit(event, user, detail)
    if first:
        send_admin_alert("SecurePass alert: cancellations blocked", text + "\n\nOpen Admin, then Cancellations, to review.")


def _cancel_page(booking, chosen="", problem=None):
    return render_template("bookings/cancel.html", booking=booking, reasons=REASONS, chosen=chosen,
                           problem=problem, needs_code=current_user.totp_enabled), (400 if problem else 200)


@bp.route("/<reference>/cancel/confirm")
@login_required
def cancel_form(reference: str):
    """The page that asks why, and for the password. Opening it never cancels anything."""
    booking = _own_booking_or_404(reference)
    if not booking.can_cancel:
        return redirect(url_for("bookings.detail", reference=reference))
    return _cancel_page(booking)


@bp.route("/<reference>/cancel", methods=["POST"])
@login_required
@limiter.limit("10 per hour", key_func=lambda: f"cancel-{current_user.get_id()}")
def cancel(reference: str):
    """Cancelling needs a reason and the password (plus the app code when two-factor is on)."""
    booking = _own_booking_or_404(reference)
    if not booking.can_cancel:
        flash("This booking is already cancelled." if booking.is_cancelled
              else "This booking can no longer be cancelled.", "info")
        return redirect(url_for("bookings.detail", reference=reference))

    chosen = clean_reason(request.form.get("reason"))
    if chosen is None:
        return _cancel_page(booking, problem="Please choose a reason.")
    ip = (request.remote_addr or "")[:45]
    if too_many_recent(current_user.id):
        _alert("cancel_burst_blocked", BURST_WINDOW, current_user, booking.reference,
               f"{current_user.email} tried to cancel more than {BURST_LIMIT} bookings in 10 minutes.")
        return _cancel_page(booking, chosen, "Too many cancellations in a short time. For your safety, "
                                             "wait ten minutes or contact support.")
    if too_many_from_address(ip):
        _alert("cancel_ip_blocked", IP_WINDOW, current_user, f"{booking.reference} from {ip}",
               f"More than {ip_limit()} cancellations in one hour came from the address {ip}.")
        return _cancel_page(booking, chosen, "Too many cancellations came from your network. "
                                             "For safety, try again later or contact support.")
    if site_paused():
        _alert("cancel_site_blocked", SITE_WINDOW, current_user, booking.reference,
               f"More than {site_limit()} bookings were cancelled in 10 minutes. New cancellations are "
               "paused until the window passes. Check the Cancellations page.")
        return _cancel_page(booking, chosen, "Cancellations are paused for a few minutes because of unusual "
                                             "activity. Please try again shortly or contact support.")
    if not current_user.check_password(request.form.get("password", "")[:128]):
        audit("cancel_refused", current_user, f"{booking.reference}: wrong password")
        return _cancel_page(booking, chosen, "That is not your current password.")
    if current_user.totp_enabled and not _second_factor_ok(current_user, request.form.get("code", "")[:40]):
        db.session.commit()
        audit("cancel_refused", current_user, f"{booking.reference}: wrong code")
        return _cancel_page(booking, chosen, "That code is not right.")

    try:
        cancel_booking(current_user.id, booking, chosen, ip)
    except BookingError as error:
        flash(str(error), "info")
    else:
        db.session.commit()  # keeps the used two-factor step
        audit("booking_cancelled", current_user, f"{booking.reference}: {chosen}")
        if recent_cancellations(current_user.id) >= BURST_LIMIT:
            audit("cancel_burst_alert", current_user, f"{BURST_LIMIT} cancellations in 10 minutes")
        db.session.refresh(booking)
        send_cancellation_notice(booking, ip)
        flash("Booking cancelled. Your seats have been released.", "success")
    return redirect(url_for("bookings.detail", reference=reference))


@bp.route("/<reference>/restore", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"], key_func=lambda: f"restore-{current_user.get_id()}")
def restore(reference: str):
    """Undo a cancellation within 24 hours. Opening the page changes nothing; only the button does."""
    booking = _own_booking_or_404(reference)
    if not booking.can_restore:
        flash("This booking can't be restored. Either it is not cancelled or the 24 hours have passed.", "info")
        return redirect(url_for("bookings.detail", reference=reference))
    if request.method == "GET":
        return render_template("bookings/restore.html", booking=booking)
    try:
        restore_booking(booking)
    except BookingError as error:
        flash(str(error), "error")
    else:
        audit("booking_restored", current_user, booking.reference)
        flash("Your booking is confirmed again. Choose your seats again if you had picked some.", "success")
    return redirect(url_for("bookings.detail", reference=reference))


@bp.route("/<reference>/seats", methods=["GET", "POST"])
@login_required
def seats(reference: str):
    booking = _own_booking_or_404(reference)
    problem = seat_problem(booking)
    status, message = 200, None
    # passenger position -> chosen seat, shown on the map
    current = {t.position: (t.seat.label if t.seat else "") for t in booking.travellers}

    if request.method == "POST" and not problem:
        posted = {t.position: request.form.get(f"seat_{t.position}", "").strip().upper()[:3]
                  for t in booking.travellers}
        current = posted
        try:
            if any(label and not is_valid_label(label) for label in posted.values()):
                raise BookingError("Choose a seat from the map.")
            choose_seats(booking, {t.id: posted[t.position] for t in booking.travellers})
        except BookingError as error:
            message, status = str(error), 400
            db.session.rollback()
        else:
            chosen = ", ".join(l for l in posted.values() if l) or "none"
            audit("seats_selected", current_user, f"{booking.reference} seats: {chosen}")
            flash("Your seats have been saved.", "success")
            return redirect(url_for("bookings.detail", reference=booking.reference))

    unavailable = set() if problem else taken_seats(booking.flight, exclude_booking_id=booking.id)
    holders = {label: position for position, label in current.items() if label}
    return render_template(
        "bookings/seats.html", booking=booking, problem=problem or message, current=current,
        holders=holders, unavailable=unavailable, rows=ROWS, left=LEFT, right=RIGHT,
        exit_rows=EXIT_ROWS, capacity=CAPACITY, free_count=CAPACITY - len(unavailable),
    ), status
