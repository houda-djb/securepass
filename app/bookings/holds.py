"""Seat holds: seats are kept for a traveller for 15 minutes while they check out.

Same trick as a booking (see service.py): the seats are taken off the flight with ONE conditional
UPDATE, so two people can never hold the same last seat. A hold that is not used expires and the
seats go back on sale. Expiry is applied lazily: every browsing request first gives back the seats
of expired holds, so no background job is needed.
"""
import time
from datetime import timedelta

from flask import current_app, request
from sqlalchemy import delete, select, update

from app.bookings.service import BookingError, booking_problem
from app.extensions import db
from app.models import Flight, SeatHold, utcnow

HOLD_MINUTES = 15
_last_sweep = 0.0


def _give_back(hold_id: int, flight_id: int, passengers: int) -> bool:
    """Delete one hold and return its seats. The delete decides who wins if two requests race."""
    gone = db.session.execute(delete(SeatHold).where(SeatHold.id == hold_id))
    if gone.rowcount != 1:
        return False
    db.session.execute(update(Flight).where(Flight.id == flight_id)
                       .values(seats_available=Flight.seats_available + passengers))
    return True


def release_expired_holds(now=None) -> int:
    """Put the seats of every expired hold back on sale. Returns how many holds expired."""
    now = now or utcnow()
    expired = db.session.execute(
        select(SeatHold.id, SeatHold.flight_id, SeatHold.passengers).where(SeatHold.expires_at <= now)).all()
    released = sum(1 for hold_id, flight_id, count in expired if _give_back(hold_id, flight_id, count))
    db.session.commit()
    return released


def release_user_holds(user_id: int) -> None:
    """Drop whatever this person is holding (before a new hold, or after they book)."""
    for hold in db.session.scalars(select(SeatHold).where(SeatHold.user_id == user_id)).all():
        _give_back(hold.id, hold.flight_id, hold.passengers)
    db.session.commit()


def active_hold(user_id: int, flight_id: int, passengers: int | None = None) -> SeatHold | None:
    """The person's unexpired hold on this flight (with this many seats, when given)."""
    query = select(SeatHold).where(SeatHold.user_id == user_id, SeatHold.flight_id == flight_id,
                                   SeatHold.expires_at > utcnow())
    if passengers is not None:
        query = query.where(SeatHold.passengers == passengers)
    return db.session.scalar(query)


def seconds_left(hold: SeatHold | None) -> int:
    return 0 if hold is None else max(0, int((hold.expires_at - utcnow()).total_seconds()))


def place_hold(user_id: int, flight: Flight, passengers: int) -> SeatHold:
    """Keep `passengers` seats on `flight` for 15 minutes. Replaces any earlier hold of this person."""
    release_user_holds(user_id)
    db.session.refresh(flight)
    problem = booking_problem(flight, passengers)
    if problem:
        raise BookingError(problem)
    claimed = db.session.execute(
        update(Flight).where(Flight.id == flight.id, Flight.seats_available >= passengers)
        .values(seats_available=Flight.seats_available - passengers))
    if claimed.rowcount != 1:
        db.session.rollback()
        raise BookingError("Sorry, those seats were just taken. Please search again.")
    hold = SeatHold(user_id=user_id, flight_id=flight.id, passengers=passengers,
                    expires_at=utcnow() + timedelta(minutes=HOLD_MINUTES))
    db.session.add(hold)
    db.session.commit()
    return hold


def consume_hold(user_id: int, flight_id: int, passengers: int) -> bool:
    """Turn a valid hold into a booking: delete it WITHOUT giving the seats back. True if one was used."""
    hold = active_hold(user_id, flight_id, passengers)
    if hold is None:
        return False
    gone = db.session.execute(delete(SeatHold).where(SeatHold.id == hold.id))
    return gone.rowcount == 1


def register(app) -> None:
    """Before browsing pages are served, give back the seats of expired holds (at most every 20 s)."""
    @app.before_request
    def _sweep():
        global _last_sweep
        if request.method != "GET" or not (request.endpoint or "").startswith(("flights.", "bookings.", "main.index")):
            return
        if not app.testing and time.monotonic() - _last_sweep < 20:
            return
        _last_sweep = time.monotonic()
        try:
            release_expired_holds()
        except Exception:  # a failed sweep must never break the page
            db.session.rollback()
            current_app.logger.exception("hold sweep failed")
