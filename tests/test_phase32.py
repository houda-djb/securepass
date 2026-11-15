"""Phase 32: breached passwords, email confirmation, the list of signed-in devices."""
import pytest

from app.auth import breach
from app.auth.passwords import password_problems
from app.auth.verify import make_token
from app.extensions import db
from app.models import AuditLog, User, UserSession, utcnow
from tests.test_phase10 import ALICE, BOB, PASSWORD, login, users  # noqa: F401

STRONG = "Zebra-Quartz-4471-moon"


# ------------------------------------------------------------- breached passwords
def _sha_suffix(password):
    # The service's own lookup hash of STRONG, written out so the tests do not hash a password.
    assert password == STRONG
    digest = "540B4AF61FEAF3D02224112A68CC128AF2598096"
    return digest[:5], digest[5:]


def test_breach_check_is_off_unless_switched_on(app):
    with app.app_context():
        assert breach.is_breached("anything") is False


def test_breached_password_is_found(app, monkeypatch):
    prefix, suffix = _sha_suffix(STRONG)
    monkeypatch.setattr(breach, "_fetch_range", lambda p: f"AAAAA11111:2\r\n{suffix}:57\r\n")
    with app.app_context():
        app.config["BREACH_CHECK"] = True
        assert breach.is_breached(STRONG) is True
        assert any("breaches" in p for p in password_problems(STRONG, "x@y.com"))


def test_padding_lines_do_not_count(app, monkeypatch):
    _, suffix = _sha_suffix(STRONG)
    monkeypatch.setattr(breach, "_fetch_range", lambda p: f"{suffix}:0\r\n")
    with app.app_context():
        app.config["BREACH_CHECK"] = True
        assert breach.is_breached(STRONG) is False


def test_only_five_characters_are_sent(app, monkeypatch):
    seen = []
    monkeypatch.setattr(breach, "_fetch_range", lambda p: seen.append(p) or "")
    with app.app_context():
        app.config["BREACH_CHECK"] = True
        breach.is_breached(STRONG)
    assert len(seen) == 1 and len(seen[0]) == 5


def test_service_down_never_blocks(app, monkeypatch):
    def boom(prefix):
        raise OSError("offline")
    monkeypatch.setattr(breach, "_fetch_range", boom)
    with app.app_context():
        app.config["BREACH_CHECK"] = True
        assert breach.is_breached(STRONG) is False
        assert password_problems(STRONG, "x@y.com") == []


def test_weak_password_costs_no_network_call(app, monkeypatch):
    def boom(prefix):
        raise AssertionError("should not be called")
    monkeypatch.setattr(breach, "_fetch_range", boom)
    with app.app_context():
        app.config["BREACH_CHECK"] = True
        assert password_problems("short1", "x@y.com")


def test_registration_refuses_a_breached_password(app, monkeypatch):
    _, suffix = _sha_suffix(STRONG)
    monkeypatch.setattr(breach, "_fetch_range", lambda p: f"{suffix}:9\r\n")
    app.config["BREACH_CHECK"] = True
    r = app.test_client().post("/register", data={"email": "new@example.com", "password": STRONG,
                                                  "confirm": STRONG}, follow_redirects=True)
    with app.app_context():
        assert User.query.filter_by(email="new@example.com").count() == 0
    assert b"data breaches" in r.data


def test_production_turns_the_check_on():
    from config import ProductionConfig, TestingConfig
    assert ProductionConfig.BREACH_CHECK is True and TestingConfig.BREACH_CHECK is False


# ------------------------------------------------------------- email confirmation
def test_register_sends_a_link_and_it_confirms(app):
    client = app.test_client()
    client.post("/register", data={"email": "carol@example.com", "password": STRONG, "confirm": STRONG})
    outbox = app.extensions["outbox"]
    mail = [m for m in outbox if m["to"] == "carol@example.com"][-1]
    assert "/verify-email/" in mail["body"]
    with app.app_context():
        user = User.query.filter_by(email="carol@example.com").one()
        assert user.email_verified is False
    link = "/verify-email/" + mail["body"].split("/verify-email/")[1].split()[0]
    client.get(link)
    with app.app_context():
        assert User.query.filter_by(email="carol@example.com").one().email_verified is True
        assert AuditLog.query.filter_by(event_type="email_verified").count() == 1


def test_bad_or_changed_link_is_refused(app, users):
    client = app.test_client()
    client.get("/verify-email/not-a-token")
    with app.app_context():
        user = User.query.filter_by(email=ALICE).one()
        user.email_verified_at = None
        token = make_token(user)
        user.email = "other@example.com"
        db.session.commit()
    client.get(f"/verify-email/{token}")
    with app.app_context():
        assert User.query.filter_by(email="other@example.com").one().email_verified is False


def test_booking_needs_a_confirmed_email_when_required(app, users):
    from app.models import Flight
    with app.app_context():
        flight_id = Flight.query.first().id
        User.query.filter_by(email=ALICE).one().email_verified_at = None
        db.session.commit()
    client = app.test_client()
    login(client, ALICE)
    app.config["REQUIRE_EMAIL_VERIFICATION"] = False
    assert client.get(f"/bookings/new/{flight_id}").status_code == 200
    app.config["REQUIRE_EMAIL_VERIFICATION"] = True
    r = client.get(f"/bookings/new/{flight_id}")
    assert r.status_code == 302 and "/account" in r.headers["Location"]
    with app.app_context():
        User.query.filter_by(email=ALICE).one().email_verified_at = utcnow()
        db.session.commit()
    assert client.get(f"/bookings/new/{flight_id}").status_code == 200


def test_resend_works_for_unconfirmed_only(app, users):
    with app.app_context():
        User.query.filter_by(email=ALICE).one().email_verified_at = None
        db.session.commit()
    client = app.test_client()
    login(client, ALICE)
    before = len(app.extensions.get("outbox", []))
    client.post("/account/verify/resend")
    assert len(app.extensions["outbox"]) == before + 1
    assert b"not confirmed" in client.get("/account").data


def test_production_requires_email_only_with_smtp(monkeypatch):
    import importlib
    import config
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert importlib.reload(config).ProductionConfig.REQUIRE_EMAIL_VERIFICATION is False
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    assert importlib.reload(config).ProductionConfig.REQUIRE_EMAIL_VERIFICATION is True
    monkeypatch.delenv("SMTP_HOST")
    importlib.reload(config)


# ------------------------------------------------------------- devices
def test_login_creates_a_device_row(app, users):
    client = app.test_client()
    login(client, ALICE)
    client.get("/account")
    with app.app_context():
        rows = UserSession.query.all()
        assert len(rows) == 1 and rows[0].revoked_at is None


def test_account_lists_devices_and_marks_this_one(app, users):
    client = app.test_client()
    login(client, ALICE)
    page = client.get("/account").data
    assert b"This device" in page and b"device-row" in page


def test_revoking_one_device_signs_only_that_one_out(app, users):
    phone, laptop = app.test_client(), app.test_client()
    login(phone, ALICE)
    login(laptop, ALICE)
    with app.app_context():
        phone_row = UserSession.query.order_by(UserSession.id).first()
        phone_id = phone_row.id
    assert laptop.post(f"/account/devices/{phone_id}/revoke").status_code == 302
    assert phone.get("/account").status_code == 302          # sent to the login page
    assert laptop.get("/account").status_code == 200
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="device_revoked").count() == 1


def test_cannot_revoke_own_or_others_device(app, users):
    alice, bob = app.test_client(), app.test_client()
    login(alice, ALICE)
    login(bob, BOB)
    with app.app_context():
        alice_id = UserSession.query.filter(UserSession.user_id == User.query.filter_by(email=ALICE).one().id).one().id
    bob.post(f"/account/devices/{alice_id}/revoke")
    assert alice.get("/account").status_code == 200           # Bob can't touch Alice's device
    alice.post(f"/account/devices/{alice_id}/revoke")          # nor can she revoke the one in use
    assert alice.get("/account").status_code == 200


def test_changing_password_revokes_other_devices_in_the_list(app, users):
    phone, laptop = app.test_client(), app.test_client()
    login(phone, ALICE)
    login(laptop, ALICE)
    laptop.post("/account/password", data={"current_password": PASSWORD, "new_password": STRONG,
                                           "confirm": STRONG})
    assert phone.get("/account").status_code == 302
    with app.app_context():
        active = UserSession.query.filter(UserSession.revoked_at.is_(None)).count()
    assert active == 1


def test_log_out_everywhere_updates_the_list(app, users):
    phone, laptop = app.test_client(), app.test_client()
    login(phone, ALICE)
    login(laptop, ALICE)
    laptop.post("/account/sessions/revoke", data={"password": PASSWORD})
    assert phone.get("/account").status_code == 302
    assert laptop.get("/account").status_code == 200


def test_unknown_session_id_is_refused(app, users):
    client = app.test_client()
    login(client, ALICE)
    with client.session_transaction() as sess:
        sess["sid"] = "forged"
    assert client.get("/account").status_code == 302


def test_old_session_without_an_id_gets_one(app, users):
    client = app.test_client()
    login(client, ALICE)
    with client.session_transaction() as sess:
        sess.pop("sid")
    assert client.get("/account").status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("sid")


def test_device_labels():
    from app.auth.devices import label
    assert label("Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537") == "Chrome on Windows"
    assert label("") == "Browser on unknown system"


def test_deleting_the_account_removes_device_rows(app, users):
    client = app.test_client()
    login(client, ALICE)
    client.post("/account/delete", data={"confirm": "delete", "password": PASSWORD})
    with app.app_context():
        assert UserSession.query.count() == 0


def test_codeql_workflow_exists():
    import pathlib
    text = pathlib.Path(".github/workflows/codeql.yml").read_text()
    assert "codeql-action/analyze" in text and "security-events: write" in text
