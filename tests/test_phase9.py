from datetime import date, datetime, time, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, Booking, Flight, Passenger, User
from app.seed import seed_demo_data

PASSWORD = "Correct-horse-42"
NEW_PASSWORD = "Another-horse-77"
ALICE, BOB = "alice@example.com", "bob@example.com"


@pytest.fixture()
def users(app):
    with app.app_context():
        for email in (ALICE, BOB):
            user = User(email=email, role="user")
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.commit()


def login(client, email=ALICE, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def a_flight(app, offset=5):
    start = datetime.combine(date.today() + timedelta(days=offset), time.min)
    with app.app_context():
        return Flight.query.filter(Flight.origin_code == "LHR", Flight.destination_code == "CDG",
                                   Flight.departs_at >= start,
                                   Flight.departs_at < start + timedelta(days=1)).one().id


def names(count, **overrides):
    data = {}
    for n in range(1, count + 1):
        data[f"first_name_{n}"], data[f"last_name_{n}"] = f"Ana{'bcdefghij'[n - 1]}", f"Smith{chr(96 + n)}"
    data.update(overrides)
    return data


def book(client, flight_id, count=1, **extra):
    data = {"passengers": str(count), **names(count)}
    data.update(extra)
    return client.post(f"/bookings/new/{flight_id}", data=data)


# ---------------- Passenger names at checkout ----------------

def test_checkout_asks_for_one_name_pair_per_passenger(app, client, users):
    login(client)
    html = client.get(f"/bookings/new/{a_flight(app)}?passengers=3").get_data(as_text=True)
    for n in (1, 2, 3):
        assert f'name="first_name_{n}"' in html and f'name="last_name_{n}"' in html
    assert 'name="first_name_4"' not in html


def test_names_are_saved_with_the_booking_in_order(app, client, users):
    login(client)
    res = book(client, a_flight(app), 2, first_name_1="  Maria  ", last_name_1="O'Brien",
               first_name_2="Jean-Luc", last_name_2="de la Cruz")
    assert res.status_code == 302
    with app.app_context():
        booking = Booking.query.one()
        assert [(t.position, t.first_name, t.last_name) for t in booking.travellers] == [
            (1, "Maria", "O'Brien"), (2, "Jean-Luc", "de la Cruz")]
    page = client.get(res.headers["Location"]).get_data(as_text=True)
    assert "Maria O&#39;Brien" in page and "Jean-Luc de la Cruz" in page and "Lead" in page


def test_unicode_names_are_accepted(app, client, users):
    login(client)
    assert book(client, a_flight(app), 1, first_name_1="Zoë", last_name_1="Müller").status_code == 302


@pytest.mark.parametrize("override, message", [
    ({"first_name_1": ""}, "Enter the first name"),
    ({"last_name_1": "   "}, "Enter the last name"),
    ({"first_name_1": "R2D2"}, "letters only"),
    ({"last_name_1": "<script>alert(1)</script>"}, "letters only"),
    ({"first_name_1": "x" * 41}, "at most 40"),
    ({"last_name_1": "Smith--Jones"}, "letters only"),
    ({"first_name_1": "-Anna"}, "letters only"),
])
def test_bad_names_are_refused_and_nothing_is_booked(app, client, users, override, message):
    login(client)
    fid = a_flight(app)
    with app.app_context():
        seats = db.session.get(Flight, fid).seats_available
    res = book(client, fid, 1, **override)
    assert res.status_code == 400 and message in res.get_data(as_text=True)
    with app.app_context():
        assert Booking.query.count() == 0 and Passenger.query.count() == 0
        assert db.session.get(Flight, fid).seats_available == seats      # no seats were taken


def test_every_passenger_needs_a_name_once_any_is_sent(app, client, users):
    login(client)
    data = {"passengers": "2", "first_name_1": "Ana", "last_name_1": "Smith"}
    res = client.post(f"/bookings/new/{a_flight(app)}", data=data)
    assert res.status_code == 400 and b"Enter the first name" in res.data
    with app.app_context():
        assert Booking.query.count() == 0


def test_the_form_keeps_what_was_typed_and_escapes_it(app, client, users):
    login(client)
    res = book(client, a_flight(app), 1, first_name_1='"><b>x</b>', last_name_1="Smith")
    html = res.get_data(as_text=True)
    assert res.status_code == 400 and "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_extra_name_fields_are_ignored(app, client, users):
    login(client)
    res = book(client, a_flight(app), 1, first_name_2="Ghost", last_name_2="Passenger")
    assert res.status_code == 302
    with app.app_context():
        assert Passenger.query.count() == 1


def test_posts_without_any_name_fields_still_book(app, client, users):
    # Older links and scripted posts send only the passenger count.
    login(client)
    res = client.post(f"/bookings/new/{a_flight(app)}", data={"passengers": "2"})
    assert res.status_code == 302
    with app.app_context():
        assert Booking.query.one().passengers == 2 and Passenger.query.count() == 0
    assert b"No passenger names were saved" in client.get(res.headers["Location"]).data


def test_names_are_not_written_to_the_audit_log(app, client, users):
    login(client)
    book(client, a_flight(app), 1, first_name_1="Zelda", last_name_1="Fitzgerald")
    with app.app_context():
        assert not any("Zelda" in (e.detail or "") for e in AuditLog.query.all())


def test_only_the_owner_can_see_passenger_names(app, client, users):
    login(client)
    reference = book(client, a_flight(app), 1, first_name_1="Private", last_name_1="Person") \
        .headers["Location"].rsplit("/", 1)[1]
    other = app.test_client()
    login(other, BOB)
    assert other.get(f"/bookings/{reference}").status_code == 404


def test_cancelling_keeps_the_passenger_names(app, client, users):
    login(client)
    location = book(client, a_flight(app), 1).headers["Location"]
    assert client.post(location + "/cancel").status_code == 302
    with app.app_context():
        assert Passenger.query.count() == 1


# ---------------- Account page ----------------

def test_account_page_needs_a_login(client):
    res = client.get("/account")
    assert res.status_code == 302 and "/login" in res.headers["Location"]
    assert client.post("/account/password", data={}).status_code == 302


def test_account_page_shows_profile_stats_and_history(app, client, users):
    login(client)
    book(client, a_flight(app), 1)
    html = client.get("/account").get_data(as_text=True)
    assert ALICE in html and "Member since" in html
    assert "Upcoming trips" in html and "Logged in" in html and "Booking made" in html
    assert html.index("Booking made") < html.index("Logged in")           # newest first
    assert client.get("/account").headers["Cache-Control"] == "no-store"


def test_history_shows_only_my_own_events(app, client, users):
    bob = app.test_client()
    login(bob, BOB)
    login(client)
    html = client.get("/account").get_data(as_text=True)
    assert html.count("Logged in") == 1


def test_navigation_links_to_the_account_page_only_when_logged_in(client, users):
    assert "/account" not in client.get("/").get_data(as_text=True)
    login(client)
    assert 'href="/account"' in client.get("/").get_data(as_text=True)


def change(client, **overrides):
    data = {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm": NEW_PASSWORD}
    data.update(overrides)
    return client.post("/account/password", data=data)


def test_password_can_be_changed_and_is_audited(app, client, users):
    login(client)
    assert change(client).status_code == 302
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="password_changed").count() == 1
        assert "Another" not in "".join(e.detail for e in AuditLog.query.all())     # never logged
    assert client.get("/account").status_code == 200                      # still logged in
    client.post("/logout")
    assert login(client).status_code == 401                                # old password is dead
    assert login(client, password=NEW_PASSWORD).status_code == 302


@pytest.mark.parametrize("override, message", [
    ({"current_password": "Wrong-password-1"}, "not your current password"),
    ({"new_password": "short1", "confirm": "short1"}, "10 characters"),
    ({"new_password": "alllettersnonumber", "confirm": "alllettersnonumber"}, "number"),
    ({"confirm": "Different-horse-9"}, "match"),
    ({"new_password": PASSWORD, "confirm": PASSWORD}, "different from the current"),
    ({"current_password": ""}, "required"),
])
def test_bad_password_changes_are_refused(app, client, users, override, message):
    login(client)
    res = change(client, **override)
    assert res.status_code == 400 and message in res.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(email=ALICE).one().check_password(PASSWORD)
        assert AuditLog.query.filter_by(event_type="password_changed").count() == 0


def test_a_wrong_current_password_is_audited(app, client, users):
    login(client)
    change(client, current_password="Wrong-password-1")
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="password_change_failed").count() == 1


def test_password_change_needs_a_csrf_token():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    with app.app_context():
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        seed_demo_data(days=2)
    client = app.test_client()
    import re
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": token})
    assert change(client).status_code == 400
    with app.app_context():
        assert User.query.one().check_password(PASSWORD)


def test_password_change_is_rate_limited():
    app = create_app("testing", {"RATELIMIT_ENABLED": True})
    with app.app_context():
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    login(client)
    codes = [change(client, current_password="Wrong-password-1").status_code for _ in range(12)]
    assert codes[:10] == [400] * 10 and codes[10] == 429
