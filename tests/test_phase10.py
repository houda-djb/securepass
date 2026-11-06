from datetime import date, datetime, time, timedelta

import pytest

from app.bookings import seats as seatmap
from app.extensions import db
from app.models import AuditLog, Booking, Flight, Passenger, SeatAssignment, User

PASSWORD = "Correct-horse-42"
ALICE, BOB = "alice@example.com", "bob@example.com"


@pytest.fixture()
def users(app):
    with app.app_context():
        for email in (ALICE, BOB):
            user = User(email=email, role="user")
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.commit()


def login(client, email=ALICE):
    return client.post("/login", data={"email": email, "password": PASSWORD})


def a_flight(app, offset=5):
    start = datetime.combine(date.today() + timedelta(days=offset), time.min)
    with app.app_context():
        return Flight.query.filter(Flight.origin_code == "LHR", Flight.destination_code == "CDG",
                                   Flight.departs_at >= start,
                                   Flight.departs_at < start + timedelta(days=1)).one().id


def book(client, flight_id, count=2):
    data = {"passengers": str(count)}
    for n in range(1, count + 1):
        data[f"first_name_{n}"], data[f"last_name_{n}"] = "Ana", "Smith"
    res = client.post(f"/bookings/new/{flight_id}", data=data)
    assert res.status_code == 302
    return res.headers["Location"].rsplit("/", 1)[1]


def free(app, flight_id, count=3):
    """The first free seats on a flight. Which seats are sold varies, so tests ask the app."""
    with app.app_context():
        taken = seatmap.taken_seats(db.session.get(Flight, flight_id))
        return [label for label in seatmap.all_labels() if label not in taken][:count]


def seats_of(app, reference):
    with app.app_context():
        booking = Booking.query.filter_by(reference=reference).one()
        return {t.position: (t.seat.label if t.seat else None) for t in booking.travellers}


# ---------------- The layout ----------------

def test_the_cabin_has_180_valid_seats():
    labels = seatmap.all_labels()
    assert len(labels) == 180 == seatmap.CAPACITY and len(set(labels)) == 180
    assert all(seatmap.is_valid_label(label) for label in labels)


@pytest.mark.parametrize("bad", ["", "0A", "31A", "1G", "A1", "12", "12AA", "1a", "<b>", "12A\n", "-1A", "１２A"])
def test_odd_seat_labels_are_invalid(bad):
    assert not seatmap.is_valid_label(bad)


# ---------------- Choosing seats ----------------

def test_seat_page_lists_every_free_seat_and_needs_a_login(app, client, users):
    anonymous = client.get("/bookings/ABCDEFGH/seats")
    assert anonymous.status_code == 302 and "/login" in anonymous.headers["Location"]
    login(client)
    reference = book(client, a_flight(app))
    html = client.get(f"/bookings/{reference}/seats").get_data(as_text=True)
    assert html.count('data-seat="') == 180 and 'name="seat_1"' in html and 'name="seat_2"' in html
    assert client.get(f"/bookings/{reference}/seats").headers["Cache-Control"] == "no-store"


def test_seats_are_saved_and_shown_on_the_booking(app, client, users):
    login(client)
    flight = a_flight(app)
    reference = book(client, flight)
    one, two, _ = free(app, flight)
    res = client.post(f"/bookings/{reference}/seats", data={"seat_1": one.lower(), "seat_2": two})
    assert res.status_code == 302
    assert seats_of(app, reference) == {1: one, 2: two}
    page = client.get(f"/bookings/{reference}").get_data(as_text=True)
    assert f"Seat {one}" in page and f"Seat {two}" in page and "Change seats" in page
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="seats_selected").count() == 1


def test_seats_can_be_changed_and_cleared(app, client, users):
    login(client)
    flight = a_flight(app)
    reference = book(client, flight)
    one, two, _ = free(app, flight)
    client.post(f"/bookings/{reference}/seats", data={"seat_1": one, "seat_2": two})
    client.post(f"/bookings/{reference}/seats", data={"seat_1": two, "seat_2": ""})
    assert seats_of(app, reference) == {1: two, 2: None}
    with app.app_context():
        assert SeatAssignment.query.count() == 1


def test_two_passengers_cannot_share_a_seat(app, client, users):
    login(client)
    reference = book(client, a_flight(app))
    res = client.post(f"/bookings/{reference}/seats", data={"seat_1": "5C", "seat_2": "5C"})
    assert res.status_code == 400 and b"different seat" in res.data
    assert seats_of(app, reference) == {1: None, 2: None}


@pytest.mark.parametrize("bad", ["99Z", "0A", "31A", "<script>", "5G", "A5"])
def test_invalid_seats_are_refused(app, client, users, bad):
    login(client)
    reference = book(client, a_flight(app))
    res = client.post(f"/bookings/{reference}/seats", data={"seat_1": bad})
    assert res.status_code == 400 and b"Choose a seat from the map" in res.data
    assert seats_of(app, reference) == {1: None, 2: None}


def test_a_seat_taken_by_another_booking_is_refused_and_looks_taken(app, client, users):
    flight = a_flight(app)
    login(client)
    mine = book(client, flight)
    bob = app.test_client()
    login(bob, BOB)
    theirs = book(bob, flight, 1)
    chosen = free(app, flight)[0]
    assert bob.post(f"/bookings/{theirs}/seats", data={"seat_1": chosen}).status_code == 302

    res = client.post(f"/bookings/{mine}/seats", data={"seat_1": chosen})
    assert res.status_code == 400 and b"no longer available" in res.data
    assert seats_of(app, mine) == {1: None, 2: None}
    html = client.get(f"/bookings/{mine}/seats").get_data(as_text=True)
    assert f'aria-label="Seat {chosen}, taken"' in html and f'<option value="{chosen}"' not in html


def test_the_database_itself_refuses_a_double_booked_seat(app, client, users):
    login(client)
    flight = a_flight(app)
    reference = book(client, flight)
    seat = free(app, flight)[0]
    client.post(f"/bookings/{reference}/seats", data={"seat_1": seat})
    with app.app_context():
        from sqlalchemy.exc import IntegrityError
        other = Passenger.query.filter_by(position=2).one()
        db.session.add(SeatAssignment(passenger_id=other.id, booking_id=other.booking_id,
                                      flight_id=flight, label=seat))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_only_the_owner_can_open_or_change_seats(app, client, users):
    login(client)
    reference = book(client, a_flight(app))
    other = app.test_client()
    login(other, BOB)
    assert other.get(f"/bookings/{reference}/seats").status_code == 404
    assert other.post(f"/bookings/{reference}/seats", data={"seat_1": "1A"}).status_code == 404
    assert seats_of(app, reference) == {1: None, 2: None}


def test_cancelling_frees_the_seats(app, client, users):
    login(client)
    flight = a_flight(app)
    reference = book(client, flight)
    one, two, _ = free(app, flight)
    client.post(f"/bookings/{reference}/seats", data={"seat_1": one, "seat_2": two})
    assert seats_of(app, reference) == {1: one, 2: two}
    assert client.post(f"/bookings/{reference}/cancel", data={"reason": "plans", "password": "Correct-horse-42"}).status_code == 302
    with app.app_context():
        assert SeatAssignment.query.count() == 0
    again = client.get(f"/bookings/{reference}/seats")
    assert b"confirmed booking" in again.data
    other = app.test_client()
    login(other, BOB)
    newer = book(other, flight, 1)
    assert other.post(f"/bookings/{newer}/seats", data={"seat_1": one}).status_code == 302


def test_a_cancelled_booking_cannot_pick_seats(app, client, users):
    login(client)
    reference = book(client, a_flight(app))
    client.post(f"/bookings/{reference}/cancel", data={"reason": "plans", "password": "Correct-horse-42"})
    res = client.post(f"/bookings/{reference}/seats", data={"seat_1": "2A"})
    assert seats_of(app, reference) == {1: None, 2: None}
    assert res.status_code in (200, 400)


def test_a_departed_flight_cannot_change_seats(app, client, users):
    login(client)
    reference = book(client, a_flight(app))
    with app.app_context():
        flight = Booking.query.filter_by(reference=reference).one().flight
        flight.departs_at = datetime.now() - timedelta(hours=1)
        flight.arrives_at = flight.departs_at + timedelta(hours=2)
        db.session.commit()
    client.post(f"/bookings/{reference}/seats", data={"seat_1": "2A"})
    assert seats_of(app, reference) == {1: None, 2: None}


def test_bookings_without_names_get_a_clear_message(app, client, users):
    login(client)
    res = client.post(f"/bookings/new/{a_flight(app)}", data={"passengers": "1"})
    reference = res.headers["Location"].rsplit("/", 1)[1]
    page = client.get(f"/bookings/{reference}/seats")
    assert b"no passenger names" in page.data and b'data-seat="' not in page.data


def test_sold_seats_match_the_flight_and_stay_the_same(app, client, users):
    login(client)
    with app.app_context():
        flight = db.session.get(Flight, a_flight(app))
        sold = seatmap.CAPACITY - flight.seats_available
        first = seatmap.taken_seats(flight)
        assert len(first) == sold and first == seatmap.taken_seats(flight)


def test_own_bookings_do_not_make_extra_seats_look_sold(app, client, users):
    login(client)
    flight_id = a_flight(app)
    with app.app_context():
        before = seatmap.CAPACITY - db.session.get(Flight, flight_id).seats_available
    reference = book(client, flight_id, 3)
    a, b, c = free(app, flight_id)
    assert client.post(f"/bookings/{reference}/seats",
                       data={"seat_1": a, "seat_2": b, "seat_3": c}).status_code == 302
    with app.app_context():
        flight = db.session.get(Flight, flight_id)
        # 3 new passengers: the total taken grows by exactly 3, and the 3 chosen seats are among them
        assert len(seatmap.taken_seats(flight)) == before + 3
        assert {a, b, c} <= seatmap.taken_seats(flight)


def test_seat_changes_need_a_csrf_token():
    import re
    from app import create_app
    from app.seed import seed_demo_data
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    with app.app_context():
        seed_demo_data(days=10)
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": token})
    with app.app_context():
        booking = Booking(reference="ZZZZZZZ2", user_id=User.query.one().id,
                          flight_id=Flight.query.filter(Flight.departs_at > datetime.now()).first().id,
                          passengers=1, total_cents=100)
        booking.travellers.append(Passenger(position=1, first_name="A", last_name="B"))
        db.session.add(booking)
        db.session.commit()
    assert client.post("/bookings/ZZZZZZZ2/seats", data={"seat_1": "1A"}).status_code == 400
    with app.app_context():
        assert SeatAssignment.query.count() == 0
