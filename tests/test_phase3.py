import re
from datetime import timedelta

import pytest

from app import create_app
from app.cli import create_admin_command, reset_db_command, seed_command
from app.extensions import db
from app.models import Airport, AuditLog, User, utcnow
from app.seed import seed_demo_data

PASSWORD = "Correct-horse-42"
ALICE = "alice@example.com"
ADMIN = "admin@example.com"


@pytest.fixture()
def users(app):
    with app.app_context():
        for email, role in ((ALICE, "user"), (ADMIN, "admin")):
            user = User(email=email, role=role)
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.commit()


def login(client, email=ALICE, password=PASSWORD, **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def events(app, event_type):
    with app.app_context():
        return AuditLog.query.filter_by(event_type=event_type).all()


# ---------------- Registration ----------------

def test_register_page_loads(client):
    res = client.get("/register")
    assert res.status_code == 200
    assert b"Create an account" in res.data


def test_register_creates_user_with_hashed_password(app, client):
    res = client.post("/register", data={"email": "  New@Example.com ", "password": PASSWORD,
                                         "confirm": PASSWORD})
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")
    with app.app_context():
        user = User.query.one()
        assert user.email == "new@example.com"          # trimmed and lowercased
        assert user.password_hash != PASSWORD            # SR1
        assert user.password_hash.startswith("scrypt:")  # AC8: a salted hash, not plain text
        assert user.role == "user"
    assert len(events(app, "register")) == 1


def test_duplicate_email_is_rejected(app, client, users):
    res = client.post("/register", data={"email": ALICE.upper(), "password": PASSWORD, "confirm": PASSWORD})
    assert res.status_code == 400
    assert b"already exists" in res.data
    with app.app_context():
        assert User.query.filter_by(email=ALICE).count() == 1


@pytest.mark.parametrize("email, password, confirm, message", [
    ("not-an-email", PASSWORD, PASSWORD, b"email"),
    ("", PASSWORD, PASSWORD, b"required"),
    ("a@example.com", "short1", "short1", b"at least 10"),
    ("a@example.com", "onlyletterslong", "onlyletterslong", b"letter and one number"),
    ("a@example.com", "1234567890123", "1234567890123", b"letter and one number"),
    ("a@example.com", PASSWORD, "different-Pass-1", b"don&#39;t match"),
    ("a@example.com", "x" * 129 + "1", "x" * 129 + "1", b"128"),
])
def test_invalid_registration_is_rejected(app, client, email, password, confirm, message):
    res = client.post("/register", data={"email": email, "password": password, "confirm": confirm})
    assert res.status_code == 400
    assert message in res.data
    with app.app_context():
        assert User.query.count() == 0


def test_password_equal_to_email_is_rejected(client):
    res = client.post("/register", data={"email": "longaddress12@example.com",
                                         "password": "longaddress12@example.com",
                                         "confirm": "longaddress12@example.com"})
    assert res.status_code == 400
    assert b"same as your email" in res.data


def test_password_is_never_echoed_back(client):
    res = client.post("/register", data={"email": "a@example.com", "password": "Secret-pass-99",
                                         "confirm": "nope"})
    assert b"Secret-pass-99" not in res.data


# ---------------- Login and logout ----------------

def test_login_success_shows_account_in_navbar(client, users):
    res = login(client, follow_redirects=True)
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert ALICE in html and "Log out" in html and "My Bookings" in html
    assert "Log in</a>" not in html


def test_wrong_password_and_unknown_email_look_identical(client, users):
    wrong = login(client, password="Wrong-password-1")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert b"Invalid email or password" in wrong.data
    assert b"Invalid email or password" in unknown.data  # no hint about which emails exist


def test_account_locks_after_five_failures(app, client, users):
    for _ in range(5):
        assert login(client, password="Wrong-password-1").status_code == 401
    # Even the correct password is refused while the account is locked (AC4).
    assert login(client).status_code == 401
    with app.app_context():
        user = User.query.filter_by(email=ALICE).one()
        assert user.failed_logins == 5 and user.is_locked()
        assert user.locked_until - utcnow() > timedelta(minutes=14)
    assert len(events(app, "account_locked")) == 1
    assert len(events(app, "login_blocked")) == 1


def test_lock_expires_and_counter_resets(app, client, users):
    with app.app_context():
        user = User.query.filter_by(email=ALICE).one()
        user.failed_logins = 5
        user.locked_until = utcnow() - timedelta(minutes=1)
        db.session.commit()
    assert login(client).status_code == 302
    with app.app_context():
        user = User.query.filter_by(email=ALICE).one()
        assert user.failed_logins == 0 and user.locked_until is None


def test_successful_login_resets_failed_counter(app, client, users):
    for _ in range(3):
        login(client, password="Wrong-password-1")
    assert login(client).status_code == 302
    with app.app_context():
        assert User.query.filter_by(email=ALICE).one().failed_logins == 0


def test_login_events_are_audited_without_secrets(app, client, users):
    login(client, password="Wrong-password-1")
    login(client)
    assert len(events(app, "login_failed")) == 1
    assert len(events(app, "login_success")) == 1
    with app.app_context():
        for entry in AuditLog.query.all():
            assert "Wrong-password-1" not in entry.detail and PASSWORD not in entry.detail


def test_session_cookie_is_http_only_and_same_site(client, users):
    res = login(client)
    cookie = res.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


@pytest.mark.parametrize("target, expected", [
    ("/bookings/", "/bookings/"),
    ("https://evil.example/steal", "/"),
    ("//evil.example", "/"),
    ("/\\evil.example", "/"),
    ("javascript:alert(1)", "/"),
])
def test_next_redirect_only_stays_on_this_site(client, users, target, expected):
    res = client.post("/login", query_string={"next": target},
                      data={"email": ALICE, "password": PASSWORD})
    assert res.status_code == 302
    assert res.headers["Location"] == expected


def test_logout_needs_post_and_ends_the_session(client, users):
    login(client)
    assert client.get("/logout").status_code == 405
    res = client.post("/logout")
    assert res.status_code == 302
    assert client.get("/bookings/").status_code == 302  # logged out: sent to the login page


def test_logged_in_user_is_redirected_away_from_login(client, users):
    login(client)
    assert client.get("/login").status_code == 302
    assert client.get("/register").status_code == 302


# ---------------- Roles and access control ----------------

def test_anonymous_is_sent_to_login(client):
    res = client.get("/admin/")
    assert res.status_code == 302
    assert "/login?next=%2Fadmin%2F" in res.headers["Location"]  # URL-encoded /admin/
    assert client.get("/bookings/").status_code == 302


def test_normal_user_gets_403_on_admin(app, client, users):
    login(client)
    res = client.get("/admin/")
    assert res.status_code == 403  # AC1
    assert b"have access to that page" in res.data
    assert len(events(app, "access_denied")) == 1


def test_admin_can_open_admin_area(client, users):
    login(client, email=ADMIN)
    assert client.get("/admin/").status_code == 200


def test_navbar_links_depend_on_role(client, users):
    assert ">Admin<" not in client.get("/").get_data(as_text=True)
    login(client)
    assert ">Admin<" not in client.get("/").get_data(as_text=True)
    client.post("/logout")
    login(client, email=ADMIN)
    assert ">Admin<" in client.get("/").get_data(as_text=True)


def test_user_roles_are_limited_by_the_database(app):
    with app.app_context():
        from sqlalchemy.exc import IntegrityError
        bad = User(email="x@example.com", role="superuser", password_hash="x")
        db.session.add(bad)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ---------------- CSRF (SR2) ----------------

@pytest.fixture()
def csrf_app():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    with app.app_context():
        seed_demo_data(days=3)
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    return app


def csrf_token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_post_without_csrf_token_is_rejected(csrf_app):
    client = csrf_app.test_client()
    assert client.post("/login", data={"email": ALICE, "password": PASSWORD}).status_code == 400  # AC3
    assert client.post("/register", data={"email": "n@example.com", "password": PASSWORD,
                                          "confirm": PASSWORD}).status_code == 400
    with csrf_app.app_context():
        assert User.query.count() == 1


def test_post_with_a_valid_csrf_token_works(csrf_app):
    client = csrf_app.test_client()
    token = csrf_token(client)
    res = client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": token})
    assert res.status_code == 302


def test_a_wrong_csrf_token_is_rejected(csrf_app):
    client = csrf_app.test_client()
    csrf_token(client)  # start a session
    res = client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": "forged"})
    assert res.status_code == 400


def test_logout_without_csrf_token_is_rejected(csrf_app):
    client = csrf_app.test_client()
    token = csrf_token(client)
    client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": token})
    assert client.post("/logout").status_code == 400
    assert client.get("/bookings/").status_code == 200  # still logged in


# ---------------- Rate limiting (SR7) ----------------

def test_login_attempts_are_rate_limited(app):
    limited = create_app("testing", {"RATELIMIT_ENABLED": True})
    client = limited.test_client()
    codes = [login(client, email="nobody@example.com").status_code for _ in range(12)]
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]


# ---------------- Command-line tools ----------------

def test_create_admin_command(app):
    runner = app.test_cli_runner()
    result = runner.invoke(create_admin_command, input="boss@example.com\nStrong-pass-77\nStrong-pass-77\n")
    assert result.exit_code == 0 and "Admin account created" in result.output
    with app.app_context():
        boss = User.query.filter_by(email="boss@example.com").one()
        assert boss.role == "admin" and boss.check_password("Strong-pass-77")


def test_create_admin_rejects_weak_password_and_duplicates(app, users):
    runner = app.test_cli_runner()
    weak = runner.invoke(create_admin_command, input="boss@example.com\nshort\nshort\n")
    assert weak.exit_code != 0 and "at least 10" in weak.output
    duplicate = runner.invoke(create_admin_command, input=f"{ALICE}\nStrong-pass-77\nStrong-pass-77\n")
    assert duplicate.exit_code != 0 and "already exists" in duplicate.output


def test_seed_does_nothing_when_data_exists(app):
    result = app.test_cli_runner().invoke(seed_command)
    assert "already there" in result.output
    with app.app_context():
        assert Airport.query.count() == 10


def test_reset_db_asks_before_deleting_and_removes_users(app, users):
    runner = app.test_cli_runner()
    refused = runner.invoke(reset_db_command, input="n\n")
    assert refused.exit_code != 0
    with app.app_context():
        assert User.query.count() == 2
    done = runner.invoke(reset_db_command, ["--yes", "--days", "2"])
    assert done.exit_code == 0
    with app.app_context():
        assert User.query.count() == 0 and Airport.query.count() == 10