"""Phase 29: seats are held for 15 minutes while a traveller checks out."""
from datetime import timedelta

from app.bookings.holds import HOLD_MINUTES, active_hold, place_hold, release_expired_holds
from app.bookings.service import BookingError
from app.extensions import db
from app.models import Flight, SeatHold, User, utcnow
from tests.test_phase10 import ALICE, BOB, a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with


def seats(app, fid):
    with app.app_context():
        return db.session.get(Flight, fid).seats_available


def holds(app):
    with app.app_context():
        return SeatHold.query.count()


def test_opening_checkout_holds_the_seats(app, client, users):
    fid = a_flight(app); before = seats(app, fid)
    login(client)
    page = client.get(f"/bookings/new/{fid}?passengers=2").get_data(as_text=True)
    assert seats(app, fid) == before - 2 and holds(app) == 1
    assert "data-hold=" in page and "Your seats are held for you." in page and "15:00" in page or "14:59" in page


def test_reloading_does_not_hold_twice(app, client, users):
    fid = a_flight(app); before = seats(app, fid)
    login(client)
    for _ in range(3):
        client.get(f"/bookings/new/{fid}?passengers=2")
    assert seats(app, fid) == before - 2 and holds(app) == 1


def test_booking_uses_the_hold_and_takes_seats_only_once(app, client, users):
    fid = a_flight(app); before = seats(app, fid)
    login(client)
    client.get(f"/bookings/new/{fid}?passengers=2")
    res = book_with(client, fid, count=2)
    assert res.status_code == 302
    assert seats(app, fid) == before - 2 and holds(app) == 0


def test_booking_without_a_hold_still_works(app, client, users):
    fid = a_flight(app); before = seats(app, fid)
    login(client)
    assert book_with(client, fid, count=1).status_code == 302
    assert seats(app, fid) == before - 1


def test_expired_hold_gives_the_seats_back(app, client, users):
    fid = a_flight(app); before = seats(app, fid)
    login(client)
    client.get(f"/bookings/new/{fid}?passengers=3")
    with app.app_context():
        SeatHold.query.update({"expires_at": utcnow() - timedelta(seconds=1)}); db.session.commit()
        assert active_hold(User.query.filter_by(email=ALICE).one().id, fid) is None
        assert release_expired_holds() == 1
    assert seats(app, fid) == before and holds(app) == 0


def test_another_traveller_cannot_take_held_seats(app, client, users):
    fid = a_flight(app)
    with app.app_context():
        db.session.get(Flight, fid).seats_available = 2; db.session.commit()
    login(client)
    client.get(f"/bookings/new/{fid}?passengers=2")
    other = app.test_client(); login(other, BOB)
    page = other.get(f"/bookings/new/{fid}?passengers=1").get_data(as_text=True)
    assert "sold out" in page.lower() and holds(app) == 1
    assert book_with(other, fid, count=1).status_code == 400


def test_a_person_has_one_hold_and_a_new_one_replaces_it(app, client, users):
    fid = a_flight(app); before = seats(app, fid)
    login(client)
    client.get(f"/bookings/new/{fid}?passengers=2")
    client.get(f"/bookings/new/{fid}?passengers=4")
    assert holds(app) == 1 and seats(app, fid) == before - 4


def test_place_hold_refuses_too_many_seats(app, users):
    fid = a_flight(app)
    with app.app_context():
        flight = db.session.get(Flight, fid); flight.seats_available = 1; db.session.commit()
        user = User.query.filter_by(email=ALICE).one()
        try:
            place_hold(user.id, flight, 2)
        except BookingError as error:
            assert "Only 1 seats" in str(error) or "left" in str(error)
        else:
            raise AssertionError("expected BookingError")


def test_hold_length_and_translation(app, client, users):
    assert HOLD_MINUTES == 15
    fid = a_flight(app)
    login(client)
    client.post("/language", data={"lang": "fr"})
    page = client.get(f"/bookings/new/{fid}").get_data(as_text=True)
    assert "Vos places sont réservées pour vous." in page
