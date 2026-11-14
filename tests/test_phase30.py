"""Phase 30: the cancellation shield (address and site limits, admin alert, 24-hour undo)."""
from datetime import timedelta

from app.extensions import db
from app.models import AuditLog, Booking, Flight, User, utcnow
from tests.test_phase10 import ALICE, BOB, PASSWORD, a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with, reference_of
from tests.test_phase21 import admin_client  # noqa: F401


def booking_for(app, email, fid):
    client = app.test_client()
    login(client, email)
    return client, reference_of(book_with(client, fid, "cash"))


def cancel(client, ref, reason="plans"):
    return client.post(f"/bookings/{ref}/cancel", data={"reason": reason, "password": PASSWORD})


def status_of(app, ref):
    with app.app_context():
        return Booking.query.filter_by(reference=ref).one().status


def seats(app, fid):
    with app.app_context():
        return db.session.get(Flight, fid).seats_available


def events(app, name):
    with app.app_context():
        return AuditLog.query.filter_by(event_type=name).count()


def outbox(app):
    return app.extensions.get("outbox", [])


# ------------------------------------------------------------------ limits

def test_one_address_cannot_cancel_without_limit(app, users, admin_client):
    app.config["CANCEL_IP_LIMIT"] = 2
    fid = a_flight(app)
    alice, a1 = booking_for(app, ALICE, fid)
    _, a2 = booking_for(app, ALICE, fid)
    bob, b1 = booking_for(app, BOB, fid)
    assert cancel(alice, a1).status_code == 302 and cancel(alice, a2).status_code == 302
    res = cancel(bob, b1)  # a different account, the same network address
    assert res.status_code == 400 and status_of(app, b1) == "confirmed"
    assert "from your network" in res.get_data(as_text=True)
    assert events(app, "cancel_ip_blocked") == 1


def test_whole_site_is_paused_after_too_many_cancellations(app, users, admin_client):
    app.config["CANCEL_SITE_LIMIT"] = 2
    fid = a_flight(app)
    alice, a1 = booking_for(app, ALICE, fid)
    bob, b1 = booking_for(app, BOB, fid)
    _, b2 = booking_for(app, BOB, fid)
    assert cancel(alice, a1).status_code == 302 and cancel(bob, b1).status_code == 302
    res = cancel(bob, b2)
    assert res.status_code == 400 and "paused" in res.get_data(as_text=True)
    assert status_of(app, b2) == "confirmed" and events(app, "cancel_site_blocked") == 1


def test_admin_is_emailed_once_when_the_shield_blocks(app, users, admin_client):
    app.config["CANCEL_SITE_LIMIT"] = 1
    fid = a_flight(app)
    alice, a1 = booking_for(app, ALICE, fid)
    bob, b1 = booking_for(app, BOB, fid)
    _, b2 = booking_for(app, BOB, fid)
    cancel(alice, a1)
    cancel(bob, b1); cancel(bob, b2)
    alerts = [m for m in outbox(app) if m["to"] == "boss@example.com"]
    assert len(alerts) == 1 and "cancellations blocked" in alerts[0]["subject"]
    assert events(app, "cancel_site_blocked") == 2  # both blocks are logged, one email is sent


def test_a_burst_on_one_account_alerts_the_admin(app, users, admin_client):
    fid = a_flight(app)
    alice, _ = booking_for(app, ALICE, fid)
    refs = [reference_of(book_with(alice, fid, "cash")) for _ in range(4)]
    for ref in refs[:3]:
        assert cancel(alice, ref).status_code == 302
    assert cancel(alice, refs[3]).status_code == 400
    assert events(app, "cancel_burst_blocked") == 1
    assert any(m["to"] == "boss@example.com" for m in outbox(app))


def test_an_undo_does_not_lower_the_site_count(app, users, admin_client):
    app.config["CANCEL_SITE_LIMIT"] = 2
    fid = a_flight(app)
    alice, a1 = booking_for(app, ALICE, fid)
    bob, b1 = booking_for(app, BOB, fid)
    _, b2 = booking_for(app, BOB, fid)
    cancel(alice, a1); cancel(bob, b1)
    alice.post(f"/bookings/{a1}/restore")
    alice.post(f"/bookings/{b1}/restore")  # not hers: refused
    assert cancel(bob, b2).status_code == 400  # still paused, the restore did not reset the count


# ------------------------------------------------------------------ undo

def test_owner_can_undo_a_cancellation_and_seats_come_back(app, users):
    fid = a_flight(app); before = seats(app, fid)
    client, ref = booking_for(app, ALICE, fid)
    count_after_booking = seats(app, fid)
    cancel(client, ref)
    assert status_of(app, ref) == "cancelled" and seats(app, fid) == before
    page = client.get(f"/bookings/{ref}").get_data(as_text=True)
    assert "Undo this cancellation" in page
    assert client.get(f"/bookings/{ref}/restore").status_code == 200
    assert status_of(app, ref) == "cancelled"  # opening the page changes nothing
    assert client.post(f"/bookings/{ref}/restore").status_code == 302
    assert status_of(app, ref) == "confirmed" and seats(app, fid) == count_after_booking
    assert events(app, "booking_restored") == 1
    with app.app_context():
        b = Booking.query.filter_by(reference=ref).one()
        assert b.cancelled_at is None and b.cancel_reason is None and b.cancelled_ip is None


def test_undo_is_refused_after_24_hours(app, users):
    fid = a_flight(app)
    client, ref = booking_for(app, ALICE, fid)
    cancel(client, ref)
    with app.app_context():
        Booking.query.filter_by(reference=ref).update({"cancelled_at": utcnow() - timedelta(hours=25)})
        db.session.commit()
    assert "Undo this cancellation" not in client.get(f"/bookings/{ref}").get_data(as_text=True)
    client.post(f"/bookings/{ref}/restore")
    assert status_of(app, ref) == "cancelled"


def test_undo_is_refused_when_the_seats_were_sold(app, users):
    fid = a_flight(app)
    client, ref = booking_for(app, ALICE, fid)
    cancel(client, ref)
    with app.app_context():
        db.session.get(Flight, fid).seats_available = 0; db.session.commit()
    res = client.post(f"/bookings/{ref}/restore", follow_redirects=True)
    assert "sold after the cancellation" in res.get_data(as_text=True)
    assert status_of(app, ref) == "cancelled" and seats(app, fid) == 0


def test_nobody_else_can_undo_my_cancellation(app, users):
    fid = a_flight(app)
    alice, ref = booking_for(app, ALICE, fid)
    cancel(alice, ref)
    bob = app.test_client(); login(bob, BOB)
    assert bob.post(f"/bookings/{ref}/restore").status_code == 404
    assert status_of(app, ref) == "cancelled"
    anon = app.test_client()
    assert anon.post(f"/bookings/{ref}/restore").status_code in (302, 401)


def test_a_confirmed_booking_cannot_be_restored(app, users):
    client, ref = booking_for(app, ALICE, a_flight(app))
    client.post(f"/bookings/{ref}/restore")
    assert status_of(app, ref) == "confirmed" and events(app, "booking_restored") == 0


def test_cancellation_email_has_an_undo_link(app, users):
    client, ref = booking_for(app, ALICE, a_flight(app))
    cancel(client, ref)
    mail = [m for m in outbox(app) if "was cancelled" in m["subject"]][-1]
    assert f"/bookings/{ref}/restore" in mail["body"] and "undo this cancellation" in mail["body"]


# ------------------------------------------------------------------ admin

def test_admin_sees_the_shield_and_can_restore(app, users, admin_client):
    fid = a_flight(app)
    client, ref = booking_for(app, ALICE, fid)
    cancel(client, ref)
    page = admin_client.get("/admin/cancellations").get_data(as_text=True)
    assert "Cancellation shield" in page and f"/admin/bookings/{ref}/restore" in page
    assert admin_client.post(f"/admin/bookings/{ref}/restore").status_code == 302
    assert status_of(app, ref) == "confirmed" and events(app, "booking_restored") == 1


def test_only_admins_can_restore_from_the_admin_page(app, users):
    fid = a_flight(app)
    client, ref = booking_for(app, ALICE, fid)
    cancel(client, ref)
    assert client.post(f"/admin/bookings/{ref}/restore").status_code == 403
    assert status_of(app, ref) == "cancelled"


def test_restore_page_is_translated(app, users):
    client, ref = booking_for(app, ALICE, a_flight(app))
    cancel(client, ref)
    client.post("/language", data={"lang": "fr"})
    assert "Restaurer ma réservation" in client.get(f"/bookings/{ref}/restore").get_data(as_text=True)
