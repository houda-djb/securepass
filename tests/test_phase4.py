import re
import threading
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.bookings.service import BookingError, create_booking
from app.extensions import db
from app.models import AuditLog, Booking, Flight, User
from app.seed import seed_demo_data

PASSWORD = "Correct-horse-42"
ALICE = "alice@example.com"
BOB = "bob@example.com"


def add_users(*emails):
    ids = []
    for email in emails:
        user = User(email=email, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.flush()
        ids.append(user.id)
    db.session.commit()
    return ids


@pytest.fixture()
def users(app):
    with app.app_context():
        add_users(ALICE, BOB)


def login(client, email=ALICE):
    return client.post("/login", data={"email": email, "password": PASSWORD})


def flight_id(app, offset=3, origin="LHR", dest="CDG"):
    start = datetime.combine(date.today() + timedelta(days=offset), time.min)
    with app.app_context():
        return Flight.query.filter(
            Flight.origin_code == origin, Flight.destination_code == dest,
            Flight.departs_at >= start, Flight.departs_at < start + timedelta(days=1)).one().id


def seats(app, fid):
    with app.app_context():
        return db.session.get(Flight, fid).seats_available


def set_seats(app, fid, n):
    with app.app_context():
        db.session.get(Flight, fid).seats_available = n
        db.session.commit()


def book(client, fid, passengers=1, **extra):
    return client.post(f"/bookings/new/{fid}", data={"passengers": passengers, **extra})


def events(app, event_type):
    with app.app_context():
        return AuditLog.query.filter_by(event_type=event_type).all()


def only_booking_reference(app, email=ALICE):
    with app.app_context():
        return Booking.query.join(User).filter(User.email == email).one().reference


# ---------------- Booking (FR9, FR10, FR14) ----------------

def test_booking_requires_login(app, client, users):
    fid = flight_id(app)
    assert client.get(f"/bookings/new/{fid}").status_code == 302
    assert book(client, fid).status_code == 302
    with app.app_context():
        assert Booking.query.count() == 0


def test_checkout_page_shows_total_and_demo_notice(app, client, users):
    fid = flight_id(app)
    login(client)
    with app.app_context():
        price = db.session.get(Flight, fid).price_cents
    html = client.get(f"/bookings/new/{fid}?passengers=3").get_data(as_text=True)
    assert "Demo payment" in html and "no card details" in html
    assert f"${price * 3 / 100:,.2f}" in html


def test_successful_booking_reduces_seats_and_is_audited(app, client, users):
    fid = flight_id(app)
    before = seats(app, fid)
    login(client)
    res = book(client, fid, passengers=2)
    assert res.status_code == 302
    with app.app_context():
        booking = Booking.query.one()
        flight = db.session.get(Flight, fid)
        assert booking.passengers == 2 and booking.status == "confirmed"
        assert booking.total_cents == flight.price_cents * 2
        assert re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", booking.reference)  # FR10
        assert flight.seats_available == before - 2
    assert res.headers["Location"].endswith(f"/bookings/{booking.reference}")
    assert len(events(app, "booking_created")) == 1


def test_references_are_random_and_not_the_row_number(app, client, users):
    fid = flight_id(app)
    login(client)
    for _ in range(5):
        book(client, fid)
    with app.app_context():
        refs = [b.reference for b in Booking.query.order_by(Booking.id)]
        assert len(set(refs)) == 5
        assert all(ref != str(i + 1) for i, ref in enumerate(refs))


def test_the_price_comes_from_the_server_not_the_browser(app, client, users):
    fid = flight_id(app)
    login(client)
    book(client, fid, passengers=1, total_cents=1, price_cents=1)
    with app.app_context():
        booking = Booking.query.one()
        assert booking.total_cents == db.session.get(Flight, fid).price_cents


@pytest.mark.parametrize("value", ["0", "10", "abc", "-1", "", "2.5"])
def test_invalid_passenger_counts_are_rejected(app, client, users, value):
    fid = flight_id(app)
    before = seats(app, fid)
    login(client)
    assert book(client, fid, passengers=value).status_code == 400
    assert seats(app, fid) == before
    with app.app_context():
        assert Booking.query.count() == 0


# ---------------- Overbooking (FR13, NFR5, AC5) ----------------

def test_cannot_book_more_seats_than_are_left(app, client, users):
    fid = flight_id(app)
    set_seats(app, fid, 2)
    login(client)
    res = book(client, fid, passengers=3)
    assert res.status_code == 400 and b"Only 2 seats" in res.data
    assert seats(app, fid) == 2


def test_last_seat_goes_to_the_first_person_only(app, client, users):
    fid = flight_id(app)
    set_seats(app, fid, 1)
    login(client)
    assert book(client, fid).status_code == 302
    assert seats(app, fid) == 0
    other = app.test_client()
    login(other, BOB)
    res = book(other, fid)
    assert res.status_code == 400 and b"sold out" in res.data
    with app.app_context():
        assert Booking.query.count() == 1


def test_a_stale_page_cannot_oversell(app, users):
    """Both people saw '1 seat left'. The database decides who gets it."""
    fid = flight_id(app)
    set_seats(app, fid, 1)
    with app.app_context():
        alice, bob = (User.query.filter_by(email=e).one().id for e in (ALICE, BOB))
        create_booking(alice, fid, 1)
        db.session.expire_all()
        with pytest.raises(BookingError):
            create_booking(bob, fid, 1)
        assert db.session.get(Flight, fid).seats_available == 0


def test_two_simultaneous_bookings_for_the_last_seat(tmp_path):
    """AC5: run two real database connections at the same moment."""
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'race.db'}"})
    with app.app_context():
        seed_demo_data(days=5)
        alice, bob = add_users(ALICE, BOB)
    fid = flight_id(app)
    set_seats(app, fid, 1)

    barrier, results = threading.Barrier(2), []

    def attempt(user_id):
        with app.app_context():
            barrier.wait()
            try:
                create_booking(user_id, fid, 1)
                results.append("booked")
            except BookingError:
                results.append("sold out")

    threads = [threading.Thread(target=attempt, args=(uid,)) for uid in (alice, bob)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["booked", "sold out"]
    with app.app_context():
        assert db.session.get(Flight, fid).seats_available == 0
        assert Booking.query.count() == 1


def test_a_departed_flight_cannot_be_booked(app, client, users):
    fid = flight_id(app)
    with app.app_context():
        db.session.get(Flight, fid).departs_at = datetime.now() - timedelta(hours=1)
        db.session.commit()
    login(client)
    res = book(client, fid)
    assert res.status_code == 400 and b"already departed" in res.data


# ---------------- My Bookings and ownership (FR11, SR6, AC2) ----------------

def test_my_bookings_lists_only_my_own(app, client, users):
    fid = flight_id(app)
    login(client)
    book(client, fid)
    ref = only_booking_reference(app)
    assert ref in client.get("/bookings/").get_data(as_text=True)

    other = app.test_client()
    login(other, BOB)
    html = other.get("/bookings/").get_data(as_text=True)
    assert ref not in html and "no bookings yet" in html


def test_booking_page_is_private_to_its_owner(app, client, users):
    fid = flight_id(app)
    login(client)
    book(client, fid)
    ref = only_booking_reference(app)
    assert client.get(f"/bookings/{ref}").status_code == 200

    other = app.test_client()
    login(other, BOB)
    assert other.get(f"/bookings/{ref}").status_code == 404  # AC2: looks like it doesn't exist
    assert len(events(app, "access_denied")) == 1             # but the attempt is recorded


@pytest.mark.parametrize("ref", ["ZZZZZZZZ", "short", "../../etc/passwd", "k7m2qx9p"])
def test_unknown_or_malformed_references_are_404(client, users, ref):
    login(client)
    assert client.get(f"/bookings/{ref}").status_code == 404


def test_anonymous_cannot_see_bookings(client):
    assert client.get("/bookings/").status_code == 302
    assert client.get("/bookings/ABCDEFGH").status_code == 302


# ---------------- Cancellation (FR12) ----------------

def test_cancel_returns_the_seats(app, client, users):
    fid = flight_id(app)
    before = seats(app, fid)
    login(client)
    book(client, fid, passengers=3)
    ref = only_booking_reference(app)
    assert seats(app, fid) == before - 3

    assert client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "Correct-horse-42"}).status_code == 302
    assert seats(app, fid) == before
    with app.app_context():
        booking = Booking.query.one()
        assert booking.status == "cancelled" and booking.cancelled_at is not None
    assert len(events(app, "booking_cancelled")) == 1


def test_cancelling_twice_returns_seats_only_once(app, client, users):
    fid = flight_id(app)
    before = seats(app, fid)
    login(client)
    book(client, fid, passengers=2)
    ref = only_booking_reference(app)
    client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "Correct-horse-42"})
    res = client.post(f"/bookings/{ref}/cancel", follow_redirects=True)
    assert b"already cancelled" in res.data
    assert seats(app, fid) == before


def test_cannot_cancel_someone_elses_booking(app, client, users):
    fid = flight_id(app)
    login(client)
    book(client, fid)
    ref = only_booking_reference(app)
    seats_after_booking = seats(app, fid)

    other = app.test_client()
    login(other, BOB)
    assert other.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "Correct-horse-42"}).status_code == 404  # AC2
    with app.app_context():
        assert Booking.query.one().status == "confirmed"
    assert seats(app, fid) == seats_after_booking


def test_cancel_needs_post_and_login(app, client, users):
    fid = flight_id(app)
    login(client)
    book(client, fid)
    ref = only_booking_reference(app)
    assert client.get(f"/bookings/{ref}/cancel").status_code == 405
    client.post("/logout")
    assert client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "Correct-horse-42"}).status_code == 302
    with app.app_context():
        assert Booking.query.one().status == "confirmed"


def test_a_departed_flight_cannot_be_cancelled(app, client, users):
    fid = flight_id(app)
    login(client)
    book(client, fid)
    ref = only_booking_reference(app)
    with app.app_context():
        db.session.get(Flight, fid).departs_at = datetime.now() - timedelta(hours=1)
        db.session.commit()
    res = client.post(f"/bookings/{ref}/cancel", follow_redirects=True)
    assert b"already departed" in res.data
    with app.app_context():
        assert Booking.query.one().status == "confirmed"


# ---------------- CSRF (SR2) ----------------

@pytest.fixture()
def csrf_app():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    with app.app_context():
        seed_demo_data(days=6)
        add_users(ALICE)
    return app


def token_from(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def csrf_login(client):
    token = token_from(client, "/login")
    client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": token})


def test_booking_and_cancel_need_a_csrf_token(csrf_app):
    client = csrf_app.test_client()
    csrf_login(client)
    fid = flight_id(csrf_app)

    assert book(client, fid).status_code == 400            # no token
    with csrf_app.app_context():
        assert Booking.query.count() == 0

    token = token_from(client, f"/bookings/new/{fid}?passengers=1")
    assert book(client, fid, csrf_token=token).status_code == 302

    ref = only_booking_reference(csrf_app)
    assert client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "Correct-horse-42"}).status_code == 400
    with csrf_app.app_context():
        assert Booking.query.one().status == "confirmed"
    token = token_from(client, f"/bookings/{ref}")
    assert client.post(f"/bookings/{ref}/cancel", data={"csrf_token": token, "reason": "plans", "password": "Correct-horse-42"}).status_code == 302


# ---------------- Flight page and database rules ----------------

def test_flight_page_shows_booking_form_only_when_logged_in(app, client, users):
    fid = flight_id(app)
    anonymous = client.get(f"/flights/{fid}").get_data(as_text=True)
    assert "Log in to book" in anonymous and "Continue to booking" not in anonymous
    login(client)
    member = client.get(f"/flights/{fid}?passengers=2").get_data(as_text=True)
    assert "Continue to booking" in member and 'value="2" selected' in member


def test_flight_page_says_when_sold_out(app, client, users):
    fid = flight_id(app)
    set_seats(app, fid, 0)
    login(client)
    html = client.get(f"/flights/{fid}").get_data(as_text=True)
    assert "sold out" in html and "Continue to booking" not in html


def test_database_rejects_impossible_bookings(app, users):
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one().id
        fid = Flight.query.first().id
        for kwargs in ({"passengers": 0}, {"passengers": 10}, {"status": "refunded"}, {"total_cents": -5}):
            fields = dict(reference="ABCDEFGH", user_id=alice, flight_id=fid,
                          passengers=1, total_cents=100, status="confirmed")
            fields.update(kwargs)
            db.session.add(Booking(**fields))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()