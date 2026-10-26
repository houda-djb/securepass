"""The seat map: one aircraft layout, and who sits where.

Every flight uses the same cabin: 30 rows with seats A-C and D-F either side of the aisle.
Our database only counts free seats (Flight.seats_available), so the map is built like this:
  * seats chosen by bookings in this system are exactly known (SeatAssignment rows);
  * every other sold seat is "sold to someone else". Which ones is picked by a fixed shuffle
    of the cabin that depends only on the flight, so the map looks the same on every visit.
A seat can never go to two people: the unique constraint on (flight, seat) is the last
line of defence if two requests arrive together.
"""
import random
import re

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.bookings.service import BookingError
from app.extensions import db
from app.models import Booking, Passenger, SeatAssignment

ROWS = range(1, 31)
LEFT, RIGHT = "ABC", "DEF"
LETTERS = LEFT + RIGHT
EXIT_ROWS = (12, 13)
CAPACITY = len(ROWS) * len(LETTERS)           # 180
LABEL_PATTERN = re.compile(r"^(?:[1-9]|[12][0-9]|30)[A-F]$")


def all_labels() -> list[str]:
    return [f"{row}{letter}" for row in ROWS for letter in LETTERS]


def is_valid_label(label: str) -> bool:
    return bool(LABEL_PATTERN.fullmatch(label))


def seat_problem(booking: Booking) -> str | None:
    """Why seats can't be chosen for this booking right now, or None."""
    if booking.status != "confirmed":
        return "Seats can only be chosen on a confirmed booking."
    if booking.flight.has_departed:
        return "This flight has already departed."
    if not booking.travellers:
        return "This booking has no passenger names, so seats can't be assigned."
    return None


def taken_seats(flight, exclude_booking_id: int | None = None) -> set[str]:
    """Seats nobody in this booking may pick: chosen in other bookings, or sold elsewhere."""
    stmt = select(SeatAssignment.label).where(SeatAssignment.flight_id == flight.id)
    if exclude_booking_id is not None:
        stmt = stmt.where(SeatAssignment.booking_id != exclude_booking_id)
    ours = set(db.session.scalars(stmt))

    ours_total = db.session.scalar(
        select(func.coalesce(func.sum(Booking.passengers), 0))
        .where(Booking.flight_id == flight.id, Booking.status == "confirmed")) or 0
    sold_elsewhere = max(0, CAPACITY - flight.seats_available - ours_total)

    order = all_labels()
    random.Random(f"flight-{flight.id}").shuffle(order)
    everyone_chosen = set(db.session.scalars(
        select(SeatAssignment.label).where(SeatAssignment.flight_id == flight.id)))
    elsewhere = [label for label in order if label not in everyone_chosen][:sold_elsewhere]
    return ours | set(elsewhere)


def choose_seats(booking: Booking, choices: dict[int, str]) -> None:
    """Replace this booking's seats. `choices` maps passenger id -> label ("" = no seat)."""
    problem = seat_problem(booking)
    if problem:
        raise BookingError(problem)
    own_ids = {p.id for p in booking.travellers}
    if set(choices) - own_ids:
        raise BookingError("Those passengers are not on this booking.")

    labels = [label for label in choices.values() if label]
    if any(not is_valid_label(label) for label in labels):
        raise BookingError("Choose a seat from the map.")
    if len(set(labels)) != len(labels):
        raise BookingError("Each passenger needs a different seat.")
    unavailable = taken_seats(booking.flight, exclude_booking_id=booking.id)
    for label in labels:
        if label in unavailable:
            raise BookingError(f"Seat {label} is no longer available. Please choose another.")

    db.session.execute(delete(SeatAssignment).where(SeatAssignment.booking_id == booking.id))
    for passenger_id, label in choices.items():
        if label:
            db.session.add(SeatAssignment(passenger_id=passenger_id, booking_id=booking.id,
                                          flight_id=booking.flight_id, label=label))
    try:
        db.session.commit()
    except IntegrityError:  # someone took a seat between our check and the save
        db.session.rollback()
        raise BookingError("Someone just took one of those seats. Please choose again.")
    db.session.expire(booking)
