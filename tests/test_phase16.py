"""Phase 16: forgot password, password reset links and a stronger password rule."""
import re
from datetime import timedelta

import pytest

from app.auth.passwords import password_problems
from app.auth.reset import make_token, user_for_token
from app.extensions import db
from app.models import AuditLog, User, utcnow

EMAIL, OLD, NEW = "bella@example.com", "Correct-horse-42", "Another-horse-77"


@pytest.fixture()
def user(app):
    with app.app_context():
        u = User(email=EMAIL, role="user")
        u.set_password(OLD)
        db.session.add(u)
        db.session.commit()
    return EMAIL


def request_link(app, client, email=EMAIL):
    client.post("/forgot-password", data={"email": email})
    outbox = app.extensions.get("outbox", [])
    return outbox[-1]["link"] if outbox else None


def token_of(link):
    return re.search(r"/reset-password/(.+)$", link).group(1)


def test_login_page_links_to_forgot_password(client):
    assert "/forgot-password" in client.get("/login").get_data(as_text=True)


def test_forgot_page_opens(client):
    assert client.get("/forgot-password").status_code == 200


def test_known_and_unknown_emails_get_the_same_answer(app, client, user):
    known = client.post("/forgot-password", data={"email": EMAIL})
    unknown = client.post("/forgot-password", data={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_data() == unknown.get_data()
    assert len(app.extensions["outbox"]) == 1          # only the real account got mail


def test_reset_flow_changes_the_password(app, client, user):
    link = request_link(app, client)
    token = token_of(link)
    assert client.get(f"/reset-password/{token}").status_code == 200
    res = client.post(f"/reset-password/{token}", data={"password": NEW, "confirm": NEW})
    assert res.status_code == 302
    assert client.post("/login", data={"email": EMAIL, "password": OLD}).status_code != 302
    assert client.post("/login", data={"email": EMAIL, "password": NEW}).status_code == 302
    with app.app_context():
        kinds = {a.event_type for a in AuditLog.query.all()}
        assert {"password_reset_requested", "password_reset"} <= kinds


def test_a_link_works_only_once(app, client, user):
    token = token_of(request_link(app, client))
    client.post(f"/reset-password/{token}", data={"password": NEW, "confirm": NEW})
    again = client.post(f"/reset-password/{token}", data={"password": "Third-horse-99", "confirm": "Third-horse-99"})
    assert again.status_code == 302 and "/forgot-password" in again.headers["Location"]
    assert client.post("/login", data={"email": EMAIL, "password": NEW}).status_code == 302


def test_expired_and_forged_links_are_refused(app, client, user):
    for bad in ("not-a-token", "a" * 600, "x.y.z"):
        res = client.get(f"/reset-password/{bad}")
        assert res.status_code == 302 and "/forgot-password" in res.headers["Location"]
    with app.app_context():
        token = make_token(User.query.one())
    with app.app_context():
        import app.auth.reset as reset
        original = reset.RESET_MINUTES
        reset.RESET_MINUTES = -1
        try:
            assert user_for_token(token) is None
        finally:
            reset.RESET_MINUTES = original


def test_weak_or_repeated_passwords_are_refused_on_reset(app, client, user):
    token = token_of(request_link(app, client))
    for password, confirm in (("short1", "short1"), (NEW, "Different-horse-1"), (OLD, OLD),
                              ("password123", "password123")):
        res = client.post(f"/reset-password/{token}", data={"password": password, "confirm": confirm})
        assert res.status_code == 400
    assert client.post("/login", data={"email": EMAIL, "password": OLD}).status_code == 302


def test_reset_unlocks_a_locked_account(app, client, user):
    with app.app_context():
        u = User.query.one()
        u.failed_logins = 5
        u.locked_until = utcnow() + timedelta(minutes=10)
        db.session.commit()
    token = token_of(request_link(app, client))
    client.post(f"/reset-password/{token}", data={"password": NEW, "confirm": NEW})
    assert client.post("/login", data={"email": EMAIL, "password": NEW}).status_code == 302


def test_the_link_never_appears_in_the_audit_log(app, client, user):
    token = token_of(request_link(app, client))
    with app.app_context():
        assert all(token not in (a.detail or "") for a in AuditLog.query.all())


def test_logged_in_users_skip_the_forgot_page(app, client, user):
    client.post("/login", data={"email": EMAIL, "password": OLD})
    assert client.get("/forgot-password").status_code == 302


@pytest.mark.parametrize("password", ["password123", "Password123", "aaaaaaaaa1", "Qwerty12345"])
def test_common_passwords_are_refused(password):
    assert any("easy to guess" in p for p in password_problems(password, "x@example.com"))


def test_a_good_password_is_still_accepted():
    assert password_problems(OLD, "x@example.com") == []
