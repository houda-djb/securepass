"""Booking rules in one place. The route functions only call these helpers.

How overbooking is prevented (FR13, NFR5):
  Seats are claimed with ONE conditional UPDATE:
      UPDATE flights SET seats_available = seats_available - N
      WHERE id = ? AND seats_available >= N
  The database performs "check and subtract" as a single step, so two people can never both
  take the last seat. If the UPDATE changes 0 rows, someone else got there first. The booking
  row is saved in the same transaction, so seats and bookings can never disagree.
"""
import secrets

from sqlalchemy import select, update

from app.extensions import db
from app.models import Booking, Flight, utcnow

MAX_PASSENGERS = 9
REFERENCE_LENGTH = 8
# No 0/O or 1/I, so a code read over the phone can't be mistaken.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class BookingError(Exception):
    """Raised with a message that is safe to show to the user."""


def new_reference() -> str:
    while True:
        code = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH))
        if db.session.scalar(select(Booking.id).where(Booking.reference == code)) is None:
            return code


def booking_problem(flight: Flight, passengers: int) -> str | None:
    """Why this flight can't be booked right now, or None if it can."""
    if flight.has_departed:
        return "This flight has already departed."
    if flight.seats_available == 0:
        return "This flight is sold out."
    if flight.seats_available < passengers:
        return f"Only {flight.seats_available} seats are left on this flight."
    return None


def create_booking(user_id: int, flight_id: int, passengers: int) -> Booking:
    if not 1 <= passengers <= MAX_PASSENGERS:
        raise BookingError(f"Choose between 1 and {MAX_PASSENGERS} passengers.")

    flight = db.session.get(Flight, flight_id)
    if flight is None:
        raise BookingError("That flight no longer exists.")
    problem = booking_problem(flight, passengers)
    if problem:
        raise BookingError(problem)

    price_cents = flight.price_cents  # the server's price, never a number from the browser
    claimed = db.session.execute(
        update(Flight)
        .where(Flight.id == flight_id, Flight.seats_available >= passengers)
        .values(seats_available=Flight.seats_available - passengers)
    )
    if claimed.rowcount != 1:  # another booking took the seats after we looked
        db.session.rollback()
        raise BookingError("Sorry, those seats were just taken. Please search again.")

    booking = Booking(reference=new_reference(), user_id=user_id, flight_id=flight_id,
                      passengers=passengers, total_cents=price_cents * passengers)
    db.session.add(booking)
    db.session.commit()  # seats and booking are saved together, or not at all
    return booking


def cancel_booking(user_id: int, booking: Booking) -> None:
    """Cancel a confirmed booking and give its seats back (FR12)."""
    if booking.flight.has_departed:
        raise BookingError("Flights that have already departed can't be cancelled.")

    # The status check is part of the UPDATE, so cancelling twice (two tabs, double click)
    # can only ever return the seats once.
    cancelled = db.session.execute(
        update(Booking)
        .where(Booking.id == booking.id, Booking.user_id == user_id, Booking.status == "confirmed")
        .values(status="cancelled", cancelled_at=utcnow())
    )
    if cancelled.rowcount != 1:
        db.session.rollback()
        raise BookingError("This booking is already cancelled.")

    db.session.execute(
        update(Flight)
        .where(Flight.id == booking.flight_id)
        .values(seats_available=Flight.seats_available + booking.passengers)
    )
    db.session.commit()