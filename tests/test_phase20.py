"""Phase 20: payment method choice, confirmation email and the e-ticket."""
import re

from app.bookings.barcode import bars
from app.bookings.payment import DEFAULT_METHOD, METHODS, clean_method
from app.extensions import db
from app.models import Booking
from tests.test_phase10 import ALICE, BOB, a_flight, login, users  # noqa: F401


def book_with(client, flight_id, method=None, count=1):
    data = {"passengers": str(count)}
    for n in range(1, count + 1):
        data[f"first_name_{n}"], data[f"last_name_{n}"] = "Ana", "Smith"
    if method is not None:
        data["payment_method"] = method
    return client.post(f"/bookings/new/{flight_id}", data=data)


def reference_of(res):
    return re.search(r"/bookings/([A-Z0-9]{8})", res.headers["Location"]).group(1)


def test_clean_method_accepts_only_known_options():
    assert clean_method("cib") == "cib"
    for bad in (None, "", "bitcoin", "CIB", "card; DROP TABLE", 5):
        assert clean_method(bad) == DEFAULT_METHOD


def test_checkout_offers_every_method(app, client, users):
    login(client)
    page = client.get(f"/bookings/new/{a_flight(app)}").get_data(as_text=True)
    for key in METHODS:
        assert f'value="{key}"' in page


def test_chosen_method_is_saved_and_shown(app, client, users):
    login(client)
    res = book_with(client, a_flight(app), "baridimob")
    ref = reference_of(res)
    with app.app_context():
        assert Booking.query.filter_by(reference=ref).one().payment_method == "baridimob"
    assert "BaridiMob" in client.get(f"/bookings/{ref}").get_data(as_text=True)


def test_forged_method_falls_back_to_card(app, client, users):
    login(client)
    ref = reference_of(book_with(client, a_flight(app), "free-money"))
    with app.app_context():
        assert Booking.query.filter_by(reference=ref).one().payment_method == "card"


def test_confirmation_email_is_queued(app, client, users):
    login(client)
    ref = reference_of(book_with(client, a_flight(app), "cash"))
    mail = app.extensions["outbox"][-1]
    assert mail["to"] == ALICE and ref in mail["body"] and f"/bookings/{ref}/ticket" in mail["body"]
    assert "cash" in mail["body"].lower()


def test_ticket_shows_reference_and_barcode(app, client, users):
    login(client)
    ref = reference_of(book_with(client, a_flight(app), "cib"))
    page = client.get(f"/bookings/{ref}/ticket").get_data(as_text=True)
    assert ref in page and "<svg" in page and "CIB card" in page and "Ana Smith" in page


def test_ticket_belongs_to_its_owner_only(app, client, users):
    login(client)
    ref = reference_of(book_with(client, a_flight(app)))
    client.get("/logout")
    other = app.test_client()
    assert other.get(f"/bookings/{ref}/ticket").status_code in (302, 401)
    login(other, BOB)
    assert other.get(f"/bookings/{ref}/ticket").status_code == 404


def test_cancelled_booking_has_no_ticket(app, client, users):
    login(client)
    ref = reference_of(book_with(client, a_flight(app)))
    client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "Correct-horse-42"})
    assert client.get(f"/bookings/{ref}/ticket").status_code == 404


def test_barcode_is_stable_and_differs_between_references():
    assert bars("ABCD2345") == bars("ABCD2345")
    assert bars("ABCD2345") != bars("WXYZ6789")


def test_payment_column_exists_after_migrations(app):
    from sqlalchemy import inspect
    with app.app_context():
        assert "payment_method" in {c["name"] for c in inspect(db.engine).get_columns("bookings")}
