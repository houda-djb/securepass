"""Phase 31: log out of every device, and two-factor login required for administrators."""
from app.auth.reset import make_token
from app.extensions import db
from app.models import AuditLog, User
from config import ProductionConfig, TestingConfig
from tests.test_phase10 import ALICE, BOB, PASSWORD, login, users  # noqa: F401
from tests.test_phase21 import admin_client  # noqa: F401

NEW_PASSWORD = "Another-strong-pass-77"


def signed_in(app, email=ALICE):
    client = app.test_client()
    login(client, email)
    return client


def is_logged_in(client) -> bool:
    return client.get("/account").status_code == 200


def event_count(app, name):
    with app.app_context():
        return AuditLog.query.filter_by(event_type=name).count()


def test_log_out_everywhere_keeps_only_this_device(app, users):
    phone, laptop = signed_in(app), signed_in(app)
    assert is_logged_in(phone) and is_logged_in(laptop)
    res = laptop.post("/account/sessions/revoke", data={"password": PASSWORD})
    assert res.status_code == 302
    assert is_logged_in(laptop) and not is_logged_in(phone)
    assert event_count(app, "sessions_revoked") == 1


def test_log_out_everywhere_needs_the_password(app, users):
    phone, laptop = signed_in(app), signed_in(app)
    laptop.post("/account/sessions/revoke", data={"password": "not-my-password-1"})
    assert is_logged_in(phone) and is_logged_in(laptop)
    assert event_count(app, "sessions_revoked") == 0 and event_count(app, "sessions_revoke_refused") == 1


def test_other_users_are_not_affected(app, users):
    alice, bob = signed_in(app), signed_in(app, BOB)
    alice.post("/account/sessions/revoke", data={"password": PASSWORD})
    assert is_logged_in(bob)


def test_changing_the_password_logs_out_other_devices(app, users):
    phone, laptop = signed_in(app), signed_in(app)
    res = laptop.post("/account/password", data={"current_password": PASSWORD, "new_password": NEW_PASSWORD,
                                                 "confirm": NEW_PASSWORD})
    assert res.status_code == 302
    assert is_logged_in(laptop) and not is_logged_in(phone)


def test_a_password_reset_logs_out_every_device(app, users):
    phone = signed_in(app)
    with app.app_context():
        token = make_token(User.query.filter_by(email=ALICE).one())
    res = app.test_client().post(f"/reset-password/{token}", data={"password": NEW_PASSWORD, "confirm": NEW_PASSWORD})
    assert res.status_code == 302 and not is_logged_in(phone)


def test_sessions_from_before_this_feature_still_work_until_the_number_changes(app, users):
    client = signed_in(app)
    with app.app_context():
        user_id = User.query.filter_by(email=ALICE).one().id
    with client.session_transaction() as s:
        s["_user_id"] = str(user_id)  # the old format: just the id
    assert is_logged_in(client)
    with app.app_context():
        User.query.filter_by(email=ALICE).one().session_epoch = 1; db.session.commit()
    assert not is_logged_in(client)


def test_garbage_user_ids_in_a_session_are_refused(app, users):
    client = signed_in(app)
    for bad in ("abc", "1:x:y", "99999999999999:0", ":", "-1:0", "9999:0"):
        with client.session_transaction() as s:
            s["_user_id"] = bad
        assert not is_logged_in(client)


def test_the_account_page_offers_the_button(app, users):
    page = signed_in(app).get("/account").get_data(as_text=True)
    assert "/account/sessions/revoke" in page and "Log out of all other devices" in page


# ------------------------------------------------------------------ administrators

def test_admin_area_needs_two_factor_when_required(app, admin_client):
    app.config["REQUIRE_ADMIN_2FA"] = True
    res = admin_client.get("/admin/")
    assert res.status_code == 302 and "/account/2fa" in res.headers["Location"]
    assert admin_client.get("/admin/cancellations").status_code == 302


def test_admin_with_two_factor_gets_in(app, admin_client):
    app.config["REQUIRE_ADMIN_2FA"] = True
    with app.app_context():
        User.query.filter_by(email="boss@example.com").one().totp_enabled = True; db.session.commit()
    assert admin_client.get("/admin/").status_code == 200


def test_the_two_factor_rule_is_off_in_tests_and_on_in_production():
    assert TestingConfig.REQUIRE_ADMIN_2FA is False
    assert ProductionConfig.REQUIRE_ADMIN_2FA is True


def test_normal_users_still_get_403_not_a_redirect(app, users):
    app.config["REQUIRE_ADMIN_2FA"] = True
    assert signed_in(app).get("/admin/").status_code == 403
