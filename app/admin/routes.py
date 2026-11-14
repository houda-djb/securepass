import math
import re
from datetime import datetime
from decimal import Decimal

from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.admin import bp
from app.admin.forms import FlightForm
from app.admin.queries import (EVENT_STYLES, EVENT_TYPES, bookings_per_day, build_chart,
                               dashboard_stats, locked_users, recent_events)
from app.admin import reports
from app.admin.scans import load_summary
from app.bookings.service import BookingError, restore_booking
from app.extensions import db
from app.models import Airline, Airport, Booking, Flight, User, utcnow
from app.security import audit

MAX_ID = 2_147_483_647
PER_PAGE = 20
AIRPORT_CODE = re.compile(r"^[A-Z]{3}$")
FLIGHT_NUMBER = re.compile(r"^[A-Z]{2}[0-9]{1,4}$")


# ---------------------------------------------------------------- dashboard

@bp.route("/")
def index():
    now = utcnow()
    chosen = request.args.get("type", "")
    return render_template(
        "admin/dashboard.html",
        stats=dashboard_stats(now),
        locked=locked_users(now),
        events=recent_events(chosen),
        chart=build_chart(bookings_per_day()),
        scan=load_summary(),
        event_types=EVENT_TYPES,
        event_styles=EVENT_STYLES,
        chosen=chosen if chosen in EVENT_TYPES else "",
    )


@bp.route("/reports")
def sales_reports():
    key = reports.clean_range(request.args.get("days"))
    return render_template("admin/reports.html", key=key, ranges=list(reports.RANGES),
                           totals=reports.summary(key), methods=reports.by_payment_method(key),
                           routes=reports.top_routes(key))


@bp.route("/cancellations")
def cancellations():
    rows, attention = reports.cancellation_rows()
    return render_template("admin/cancellations.html", rows=rows, attention=attention,
                           shield=reports.shield_status())


@bp.route("/bookings/<reference>/restore", methods=["POST"])
def restore_cancelled(reference: str):
    """An administrator brings back a booking that was cancelled by mistake or by an attacker."""
    booking = db.session.scalar(select(Booking).where(Booking.reference == reference[:8]))
    if booking is None:
        abort(404)
    try:
        restore_booking(booking, by_admin=True)
    except BookingError as error:
        flash(str(error), "error")
    else:
        audit("booking_restored", current_user, f"{booking.reference}: restored by an administrator")
        flash(f"Booking {booking.reference} was restored.", "success")
    return redirect(url_for("admin.cancellations"))


@bp.route("/reports/bookings.csv")
def export_bookings():
    key = reports.clean_range(request.args.get("days"))
    audit("report_exported", current_user, f"bookings last {key} days")
    return Response(reports.bookings_csv(key), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="securepass-bookings-{key}d.csv"',
        "Cache-Control": "no-store"})


@bp.route("/users/<int:user_id>/unlock", methods=["POST"])
def unlock_user(user_id: int):
    if user_id > MAX_ID:
        abort(404)
    user = db.get_or_404(User, user_id)
    user.failed_logins = 0
    user.locked_until = None
    audit("account_unlocked", current_user, user.email)  # also saves the change above
    flash(f"{user.email} has been unlocked.", "success")
    return redirect(url_for("admin.index"))


# ------------------------------------------------------------------ flights

def _flight_or_404(flight_id: int) -> Flight:
    if flight_id > MAX_ID:
        abort(404)
    return db.get_or_404(Flight, flight_id)


def _flight_form(data=None) -> FlightForm:
    form = FlightForm(data=data)
    choices = [("", "Choose an airport")] + [
        (a.code, a.label) for a in db.session.scalars(select(Airport).order_by(Airport.city))]
    form.origin.choices = choices
    form.destination.choices = choices
    form.airline.choices = [("", "No airline recorded")] + [
        (a.code, f"{a.name} ({a.code})") for a in db.session.scalars(select(Airline).order_by(Airline.name))]
    return form


def _form_data(flight: Flight) -> dict:
    return {
        "flight_no": flight.flight_no, "origin": flight.origin_code,
        "destination": flight.destination_code, "departs_at": flight.departs_at,
        "arrives_at": flight.arrives_at, "price": Decimal(flight.price_cents) / 100,
        "seats_available": flight.seats_available, "airline": flight.airline_code or "",
    }


def _apply(flight: Flight, form: FlightForm) -> None:
    flight.flight_no = form.flight_no.data
    flight.origin_code = form.origin.data
    flight.destination_code = form.destination.data
    flight.departs_at = form.departs_at.data
    flight.arrives_at = form.arrives_at.data
    flight.price_cents = int((form.price.data * 100).to_integral_value())  # money as whole cents
    flight.seats_available = form.seats_available.data
    flight.airline_code = form.airline.data or None


@bp.route("/flights")
def flights():
    query = request.args.get("q", "").strip().upper()[:12]
    note = None
    stmt = select(Flight).where(Flight.departs_at >= datetime.now())
    if query:
        if AIRPORT_CODE.match(query):
            stmt = stmt.where(or_(Flight.origin_code == query, Flight.destination_code == query))
        elif FLIGHT_NUMBER.match(query):
            stmt = stmt.where(Flight.flight_no == query)
        else:
            note = "Search by flight number (for example SP104) or airport code (for example LHR)."

    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pages = max(1, math.ceil(total / PER_PAGE))
    raw_page = request.args.get("page", "1")
    page = int(raw_page) if raw_page.isascii() and raw_page.isdigit() and int(raw_page) >= 1 else 1
    page = min(page, pages)

    rows = db.session.scalars(
        stmt.options(joinedload(Flight.origin), joinedload(Flight.destination))
        .order_by(Flight.departs_at, Flight.id).limit(PER_PAGE).offset((page - 1) * PER_PAGE)
    ).all()
    has_bookings = set(db.session.scalars(
        select(Booking.flight_id).where(Booking.flight_id.in_([f.id for f in rows]))).all())
    return render_template("admin/flights.html", flights=rows, has_bookings=has_bookings,
                           query=query, note=note, page=page, pages=pages, total=total)


@bp.route("/flights/new", methods=["GET", "POST"])
def new_flight():
    form = _flight_form()
    if form.validate_on_submit():
        flight = Flight()
        _apply(flight, form)
        db.session.add(flight)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.flight_no.errors = [*form.flight_no.errors,
                                     "A flight with this number already departs at that time."]
        else:
            audit("flight_created", current_user, f"{flight.flight_no} {flight.departs_at:%Y-%m-%d %H:%M}")
            flash(f"Flight {flight.flight_no} was added.", "success")
            return redirect(url_for("admin.flights"))
    status = 400 if form.is_submitted() else 200
    return render_template("admin/flight_form.html", form=form, flight=None, problem=None), status


@bp.route("/flights/<int:flight_id>/edit", methods=["GET", "POST"])
def edit_flight(flight_id: int):
    flight = _flight_or_404(flight_id)
    form = _flight_form(data=_form_data(flight))
    problem = None

    if form.validate_on_submit():
        confirmed = db.session.scalar(select(func.count(Booking.id)).where(
            Booking.flight_id == flight.id, Booking.status == "confirmed")) or 0
        changes_schedule = (form.flight_no.data, form.origin.data, form.destination.data,
                            form.departs_at.data, form.arrives_at.data) != (
            flight.flight_no, flight.origin_code, flight.destination_code,
            flight.departs_at, flight.arrives_at)
        if confirmed and changes_schedule:
            problem = (f"This flight has {confirmed} confirmed booking(s), so its number, route and "
                       "times can't change. You can still change the price and the seats.")
        else:
            _apply(flight, form)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.flight_no.errors = [*form.flight_no.errors,
                                         "A flight with this number already departs at that time."]
            else:
                audit("flight_updated", current_user, f"{flight.flight_no} {flight.departs_at:%Y-%m-%d %H:%M}")
                flash(f"Flight {flight.flight_no} was updated.", "success")
                return redirect(url_for("admin.flights"))
    status = 400 if form.is_submitted() else 200
    return render_template("admin/flight_form.html", form=form, flight=flight, problem=problem), status


@bp.route("/flights/<int:flight_id>/delete", methods=["POST"])
def delete_flight(flight_id: int):
    flight = _flight_or_404(flight_id)
    booked = db.session.scalar(
        select(func.count(Booking.id)).where(Booking.flight_id == flight.id)) or 0
    if booked:
        flash(f"Flight {flight.flight_no} has bookings, so it can't be deleted. "
              "Set its seats to 0 to stop new bookings.", "info")
        return redirect(url_for("admin.flights"))
    label = f"{flight.flight_no} {flight.departs_at:%Y-%m-%d %H:%M}"
    db.session.delete(flight)
    db.session.commit()
    audit("flight_deleted", current_user, label)
    flash(f"Flight {label} was deleted.", "success")
    return redirect(url_for("admin.flights"))