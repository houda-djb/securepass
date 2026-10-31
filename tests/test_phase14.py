"""Phase 14: the admin chooses the operating airline on the flight form."""
from datetime import date, datetime, time, timedelta

import pytest

from app.extensions import db
from app.models import Airline, AuditLog, Booking, Flight, User

PASSWORD = "Correct-horse-42"
ADMIN = "admin@example.com"


@pytest.fixture()
def admin(app, client):
    with app.app_context():
        user = User(email=ADMIN, role="admin")
        user.set_password(PASSWORD)
        db.session.add_all([user, Airline(code="XA", name="Test Air"),
                            Airline(code="XB", name="Other Air")])
        db.session.commit()
    client.post("/login", data={"email": ADMIN, "password": PASSWORD})
    return client


def payload(**overrides):
    day = date.today() + timedelta(days=60)
    data = {"flight_no": "SP950", "origin": "LHR", "destination": "FCO",
            "departs_at": f"{day}T09:30", "arrives_at": f"{day}T12:45",
            "price": "99.00", "seats_available": "100"}
    data.update(overrides)
    return data


def test_form_lists_the_airlines(admin):
    html = admin.get("/admin/flights/new").get_data(as_text=True)
    assert "Test Air (XA)" in html and "No airline recorded" in html


def test_flight_can_be_created_with_an_airline(app, admin):
    assert admin.post("/admin/flights/new", data=payload(airline="XA")).status_code == 302
    with app.app_context():
        flight = Flight.query.filter_by(flight_no="SP950").one()
        assert flight.airline_code == "XA"
        assert AuditLog.query.filter_by(event_type="flight_created").count() == 1


def test_airline_is_optional(app, admin):
    assert admin.post("/admin/flights/new", data=payload()).status_code == 302
    with app.app_context():
        assert Flight.query.filter_by(flight_no="SP950").one().airline_code is None


def test_unknown_airline_is_rejected(app, admin):
    res = admin.post("/admin/flights/new", data=payload(airline="ZZ"))
    assert res.status_code == 400
    with app.app_context():
        assert Flight.query.filter_by(flight_no="SP950").count() == 0


def test_airline_can_be_changed_and_cleared(app, admin):
    admin.post("/admin/flights/new", data=payload(airline="XA"))
    with app.app_context():
        fid = Flight.query.filter_by(flight_no="SP950").one().id
    page = admin.get(f"/admin/flights/{fid}/edit").get_data(as_text=True)
    assert 'selected value="XA"' in page or 'value="XA" selected' in page
    assert admin.post(f"/admin/flights/{fid}/edit", data=payload(airline="XB")).status_code == 302
    with app.app_context():
        assert db.session.get(Flight, fid).airline_code == "XB"
    admin.post(f"/admin/flights/{fid}/edit", data=payload(airline=""))
    with app.app_context():
        assert db.session.get(Flight, fid).airline_code is None


def test_flights_list_shows_the_airline_name(admin):
    admin.post("/admin/flights/new", data=payload(airline="XA"))
    assert "Test Air" in admin.get("/admin/flights?q=SP950").get_data(as_text=True)
