import re

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.bookings import bp
from app.bookings.forms import BookingForm
from app.bookings.service import (MAX_PASSENGERS, BookingError, booking_problem, cancel_booking,
                                  create_booking)
from app.extensions import db
from app.models import Booking, Flight
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
        select(Booking).options(_with_flight_details())
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
def new(flight_id: int):
    if flight_id > MAX_ID:
        abort(404)
    flight = db.get_or_404(Flight, flight_id)

    status, message = 200, None
    form = BookingForm()
    if request.method == "POST":
        if form.validate_on_submit():
            passengers = form.passengers.data
            try:
                booking = create_booking(current_user.id, flight.id, passengers)
            except BookingError as error:
                message, status = str(error), 400
            else:
                audit("booking_created", current_user,
                      f"{booking.reference} {flight.flight_no} x{passengers}")
                flash("Booking confirmed. Your reference is " + booking.reference + ".", "success")
                return redirect(url_for("bookings.detail", reference=booking.reference))
        else:
            message, status = f"Choose between 1 and {MAX_PASSENGERS} passengers.", 400
        passengers = _clamp_passengers(form.passengers.data)
    else:
        passengers = _clamp_passengers(request.args.get("passengers"))

    form = BookingForm(formdata=None, passengers=passengers)  # fresh form with a fresh token
    db.session.refresh(flight)
    problem = message or booking_problem(flight, passengers)
    return render_template("bookings/checkout.html", flight=flight, form=form,
                           passengers=passengers, problem=problem,
                           total_cents=flight.price_cents * passengers), status


@bp.route("/<reference>")
@login_required
def detail(reference: str):
    return render_template("bookings/detail.html", booking=_own_booking_or_404(reference))


@bp.route("/<reference>/cancel", methods=["POST"])
@login_required
def cancel(reference: str):
    booking = _own_booking_or_404(reference)
    try:
        cancel_booking(current_user.id, booking)
    except BookingError as error:
        flash(str(error), "info")
    else:
        audit("booking_cancelled", current_user, booking.reference)
        flash("Booking cancelled. Your seats have been released.", "success")
    return redirect(url_for("bookings.detail", reference=reference))