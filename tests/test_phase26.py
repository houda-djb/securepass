"""Phase 26: cancellations must be deliberate, explained and traceable."""
from app.bookings.cancellation import REASONS, clean_reason, reason_label
from app.extensions import db
from app.models import AuditLog, Booking, User
from tests.test_phase10 import ALICE, BOB, PASSWORD, a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with, reference_of


def make(client, app):
    return reference_of(book_with(client, a_flight(app), "cash"))


def status_of(app, ref):
    with app.app_context():
        return Booking.query.filter_by(reference=ref).one().status


def test_cancel_page_asks_for_a_reason_and_password(app, client, users):
    login(client)
    page = client.get(f"/bookings/{make(client, app)}/cancel").get_data(as_text=True)
    assert 'name="reason"' in page and 'name="password"' in page and 'name="csrf_token"' in page


def test_cancel_without_reason_is_refused(app, client, users):
    login(client)
    ref = make(client, app)
    res = client.post(f"/bookings/{ref}/cancel", data={"password": PASSWORD})
    assert res.status_code == 400 and status_of(app, ref) == "confirmed"


def test_cancel_with_unknown_reason_is_refused(app, client, users):
    login(client)
    ref = make(client, app)
    assert client.post(f"/bookings/{ref}/cancel", data={"reason": "<b>x</b>", "password": PASSWORD}).status_code == 400
    assert clean_reason("hacked") is None and clean_reason("plans") == "plans"


def test_cancel_with_wrong_password_is_refused_and_logged(app, client, users):
    login(client)
    ref = make(client, app)
    res = client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": "not-my-password-1"})
    assert res.status_code == 400 and status_of(app, ref) == "confirmed"
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="cancel_refused").count() == 1


def test_a_get_request_never_cancels(app, client, users):
    login(client)
    ref = make(client, app)
    client.get(f"/bookings/{ref}/cancel")
    assert status_of(app, ref) == "confirmed"


def test_cancel_stores_reason_and_address_and_emails_the_owner(app, client, users):
    login(client)
    ref = make(client, app)
    res = client.post(f"/bookings/{ref}/cancel", data={"reason": "cheaper", "password": PASSWORD})
    assert res.status_code == 302
    with app.app_context():
        b = Booking.query.filter_by(reference=ref).one()
        assert b.status == "cancelled" and b.cancel_reason == "cheaper" and b.cancelled_ip
    mail = app.extensions["outbox"][-1]
    assert mail["to"] == ALICE and ref in mail["body"] and "was cancelled" in mail["subject"]
    assert "If it was not you" in mail["body"]


def test_only_the_owner_can_cancel(app, client, users):
    login(client)
    ref = make(client, app)
    other = app.test_client()
    login(other, BOB)
    assert other.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": PASSWORD}).status_code == 404
    assert status_of(app, ref) == "confirmed"


def test_four_cancellations_in_ten_minutes_are_stopped(app, client, users):
    login(client)
    refs = [make(client, app) for _ in range(4)]
    for ref in refs[:3]:
        assert client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": PASSWORD}).status_code == 302
    res = client.post(f"/bookings/{refs[3]}/cancel", data={"reason": "plans", "password": PASSWORD})
    assert res.status_code == 400 and status_of(app, refs[3]) == "confirmed"
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="cancel_burst_alert").count() == 1
        assert AuditLog.query.filter_by(event_type="cancel_burst_blocked").count() == 1


def test_two_factor_account_must_give_a_code(app, client, users):
    login(client)
    with app.app_context():
        user = User.query.filter_by(email=ALICE).one()
        user.totp_enabled, user.totp_secret = True, "JBSWY3DPEHPK3PXP"
        db.session.commit()
    ref = make(client, app)
    res = client.post(f"/bookings/{ref}/cancel", data={"reason": "plans", "password": PASSWORD})
    assert res.status_code == 400 and status_of(app, ref) == "confirmed"


def test_admin_sees_who_cancelled_and_why(app, client, users):
    login(client)
    ref = make(client, app)
    client.post(f"/bookings/{ref}/cancel", data={"reason": "dates", "password": PASSWORD})
    with app.app_context():
        boss = User(email="boss@example.com", role="admin")
        boss.set_password(PASSWORD)
        db.session.add(boss)
        db.session.commit()
    admin = app.test_client()
    admin.post("/login", data={"email": "boss@example.com", "password": PASSWORD})
    page = admin.get("/admin/cancellations").get_data(as_text=True)
    assert ref in page and ALICE in page and reason_label("dates") in page


def test_cancellations_page_is_for_admins_only(client, users):
    assert client.get("/admin/cancellations").status_code in (302, 401, 403)
    login(client)
    assert client.get("/admin/cancellations").status_code == 403


def test_every_reason_has_a_label():
    assert all(reason_label(k) == v for k, v in REASONS.items()) and reason_label(None) == "No reason recorded"
