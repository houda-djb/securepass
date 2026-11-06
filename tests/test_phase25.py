"""Phase 25: download your data, delete your account, security.txt."""
import json

from app.extensions import db
from app.models import AuditLog, Booking, Flight, Passenger, User
from tests.test_phase10 import ALICE, BOB, PASSWORD, a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with, reference_of


def test_export_contains_my_data_and_no_secrets(app, client, users):
    login(client)
    ref = reference_of(book_with(client, a_flight(app), "cib"))
    res = client.get("/account/export")
    assert res.status_code == 200 and "attachment" in res.headers["Content-Disposition"]
    data = json.loads(res.get_data(as_text=True))
    assert data["account"]["email"] == ALICE
    assert data["bookings"][0]["reference"] == ref and data["bookings"][0]["passengers"][0]["name"] == "Ana Smith"
    text = res.get_data(as_text=True)
    assert "password_hash" not in text and "scrypt" not in text and "totp_secret" not in text


def test_export_needs_a_login(client):
    assert client.get("/account/export").status_code in (302, 401)


def test_export_only_has_my_bookings(app, client, users):
    other = app.test_client()
    login(other, BOB)
    book_with(other, a_flight(app))
    login(client)
    assert json.loads(client.get("/account/export").get_data(as_text=True))["bookings"] == []


def test_delete_needs_the_word_and_the_password(app, client, users):
    login(client)
    client.post("/account/delete", data={"confirm": "delete", "password": "wrong-password-1"})
    client.post("/account/delete", data={"confirm": "no", "password": PASSWORD})
    with app.app_context():
        assert User.query.filter_by(email=ALICE).count() == 1


def test_delete_removes_account_bookings_and_gives_seats_back(app, client, users):
    login(client)
    fid = a_flight(app)
    with app.app_context():
        before = db.session.get(Flight, fid).seats_available
    book_with(client, fid, "cash", count=2)
    res = client.post("/account/delete", data={"confirm": "delete", "password": PASSWORD})
    assert res.status_code == 302
    with app.app_context():
        assert User.query.filter_by(email=ALICE).count() == 0
        assert Booking.query.count() == 0 and Passenger.query.count() == 0
        assert db.session.get(Flight, fid).seats_available == before
        assert AuditLog.query.filter_by(event_type="account_deleted").count() == 1
        assert AuditLog.query.filter(AuditLog.user_id.isnot(None), AuditLog.event_type == "account_deleted").count() == 0
    assert client.get("/bookings/").status_code in (302, 401)


def test_only_admin_cannot_delete_account(app, client):
    with app.app_context():
        boss = User(email="boss@example.com", role="admin")
        boss.set_password(PASSWORD)
        db.session.add(boss)
        db.session.commit()
    client.post("/login", data={"email": "boss@example.com", "password": PASSWORD})
    client.post("/account/delete", data={"confirm": "delete", "password": PASSWORD})
    with app.app_context():
        assert User.query.filter_by(email="boss@example.com").count() == 1


def test_account_page_offers_both_actions(client, users):
    login(client)
    page = client.get("/account").get_data(as_text=True)
    assert "Download my data" in page and "Delete my account" in page and 'name="csrf_token"' in page


def test_security_txt_is_published(client):
    res = client.get("/.well-known/security.txt")
    assert res.status_code == 200 and res.mimetype == "text/plain"
    text = res.get_data(as_text=True)
    assert text.startswith("Contact: https://") and "Expires: " in text
