import base64
import re
import time

import pytest

from app import create_app
from app.auth import totp
from app.extensions import db
from app.models import AuditLog, RecoveryCode, User
from app.seed import seed_demo_data

PASSWORD = "Correct-horse-42"
ALICE = "alice@example.com"


# ---------------- The code maths (RFC 4226 and 6238 test vectors) ----------------

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize("seconds, expected", [(59, "287082"), (1111111109, "081804"),
                                               (1111111111, "050471"), (2000000000, "279037")])
def test_codes_match_the_published_test_vectors(seconds, expected):
    assert totp.code_at(RFC_SECRET, seconds // 30) == expected


def test_a_code_is_accepted_in_its_slot_and_the_neighbouring_ones_only():
    now = 1_700_000_000
    code = totp.code_at(RFC_SECRET, totp.current_step(now))
    assert totp.verify(RFC_SECRET, code, now=now) == totp.current_step(now)
    assert totp.verify(RFC_SECRET, code, now=now + 30) is not None       # one slot late
    assert totp.verify(RFC_SECRET, code, now=now - 30) is not None       # one slot early
    assert totp.verify(RFC_SECRET, code, now=now + 120) is None           # far too old


def test_a_code_cannot_be_used_twice():
    now = 1_700_000_000
    code = totp.code_at(RFC_SECRET, totp.current_step(now))
    step = totp.verify(RFC_SECRET, code, now=now)
    assert totp.verify(RFC_SECRET, code, last_step=step, now=now) is None


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 34", "１２３４５６", None])
def test_malformed_codes_are_refused(bad):
    assert totp.verify(RFC_SECRET, bad, now=1_700_000_000) is None


def test_spaces_in_a_code_are_ignored():
    now = 1_700_000_000
    code = totp.code_at(RFC_SECRET, totp.current_step(now))
    assert totp.verify(RFC_SECRET, f"{code[:3]} {code[3:]}", now=now) is not None


def test_secrets_are_random_base32_of_160_bits():
    first, second = totp.new_secret(), totp.new_secret()
    assert first != second and len(first) == 32 and re.fullmatch(r"[A-Z2-7]{32}", first)


def test_the_app_link_names_the_site_and_the_account():
    uri = totp.otpauth_uri(RFC_SECRET, "a+b@example.com")
    assert uri.startswith("otpauth://totp/SecurePass%3Aa%2Bb%40example.com?secret=" + RFC_SECRET)
    assert "issuer=SecurePass" in uri


def test_recovery_codes_are_unique_and_hashed_with_a_key():
    codes = totp.new_recovery_codes()
    assert len(set(codes)) == 8 and all(re.fullmatch(r"[A-Z2-9]{5}-[A-Z2-9]{5}", c) for c in codes)
    one = totp.hash_recovery(codes[0], "key-one")
    assert one == totp.hash_recovery(codes[0].lower().replace("-", " "), "key-one")   # typing style doesn't matter
    assert one != totp.hash_recovery(codes[0], "key-two") and codes[0] not in one


# ---------------- Using it in the site ----------------

@pytest.fixture()
def alice(app):
    with app.app_context():
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()


def login(client, password=PASSWORD):
    return client.post("/login", data={"email": ALICE, "password": password})


def now_code(secret, offset=0):
    return totp.code_at(secret, totp.current_step() + offset)


def turn_on(app, client):
    """Log in, run the setup page, return (secret, recovery_codes)."""
    login(client)
    page = client.get("/account/2fa").get_data(as_text=True)
    shown = re.search(r'class="secret-key"[^>]*>([^<]+)<', page).group(1).replace(" ", "").strip()
    res = client.post("/account/2fa", data={"code": now_code(shown)})
    assert res.status_code == 200
    codes = re.findall(r"<li>([A-Z2-9]{5}-[A-Z2-9]{5})</li>", res.get_data(as_text=True))
    return shown, codes


def test_setup_page_shows_a_qr_code_and_a_key(app, client, alice):
    login(client)
    html = client.get("/account/2fa").get_data(as_text=True)
    assert "<svg" in html and "QR code for your authenticator app" in html
    assert re.search(r'class="secret-key"[^>]*>([A-Z2-7 ]{39})<', html)
    assert 'style="' not in html


def test_setup_needs_a_login(client):
    assert client.get("/account/2fa").status_code == 302
    assert client.post("/account/2fa", data={"code": "123456"}).status_code == 302


def test_a_wrong_code_does_not_turn_it_on(app, client, alice):
    login(client)
    client.get("/account/2fa")
    res = client.post("/account/2fa", data={"code": "000000"})
    assert res.status_code == 400 and b"not right" in res.data
    with app.app_context():
        assert User.query.one().totp_enabled is False and User.query.one().totp_secret is None


def test_turning_it_on_saves_the_secret_and_shows_recovery_codes_once(app, client, alice):
    secret, codes = turn_on(app, client)
    assert len(codes) == 8
    with app.app_context():
        user = User.query.one()
        assert user.totp_enabled and user.totp_secret == secret
        stored = [r.code_hash for r in RecoveryCode.query]
        assert len(stored) == 8 and not any(c.replace("-", "") in h for c in codes for h in stored)
        assert AuditLog.query.filter_by(event_type="two_factor_enabled").count() == 1
    assert not re.search(r"[A-Z2-9]{5}-[A-Z2-9]{5}", client.get("/account").get_data(as_text=True))  # never shown again
    assert client.get("/account/2fa").status_code == 302                  # already on: back to the account page


def test_login_then_needs_the_code(app, client, alice):
    secret, _ = turn_on(app, client)
    client.post("/logout")
    other = app.test_client()
    res = login(other)
    assert res.status_code == 302 and "/login/verify" in res.headers["Location"]
    assert other.get("/bookings/").status_code == 302                    # not logged in yet
    assert "/login" in other.get("/bookings/").headers["Location"]
    assert b"Two-step check" in other.get("/login/verify").data
    ok = other.post("/login/verify", data={"code": now_code(secret, +1)})   # +1: the setup used this slot
    assert ok.status_code == 302
    assert other.get("/bookings/").status_code == 200                    # now logged in
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="login_success").count() >= 2


def test_the_verify_page_needs_a_correct_password_first(app, client, alice):
    turn_on(app, client)
    stranger = app.test_client()
    assert stranger.get("/login/verify").status_code == 302
    assert stranger.post("/login/verify", data={"code": "123456"}).status_code == 302
    wrong = login(stranger, "Wrong-password-1")
    assert wrong.status_code == 401 and stranger.get("/login/verify").status_code == 302


def test_a_wrong_code_is_refused_and_counted(app, client, alice):
    secret, _ = turn_on(app, client)
    other = app.test_client()
    login(other)
    res = other.post("/login/verify", data={"code": "000000"})
    assert res.status_code == 401 and b"not right" in res.data
    with app.app_context():
        assert User.query.one().failed_logins == 1
        assert AuditLog.query.filter_by(event_type="two_factor_failed").count() == 1


def test_too_many_wrong_codes_lock_the_account(app, client, alice):
    secret, _ = turn_on(app, client)
    other = app.test_client()
    login(other)
    for _ in range(4):
        assert other.post("/login/verify", data={"code": "000000"}).status_code == 401
    last = other.post("/login/verify", data={"code": "000000"})
    assert last.status_code == 302 and "/login" in last.headers["Location"]
    with app.app_context():
        assert User.query.one().is_locked()
    assert other.post("/login/verify", data={"code": now_code(secret, +1)}).status_code == 302   # session was cleared
    fresh = app.test_client()
    res = login(fresh)
    assert res.status_code == 401                                         # locked: not even the code page


def test_a_code_can_only_be_used_once(app, client, alice):
    secret, _ = turn_on(app, client)     # the setup already used this time slot
    client.post("/logout")
    other = app.test_client()
    login(other)
    res = other.post("/login/verify", data={"code": now_code(secret)})
    assert res.status_code == 401        # same slot as the setup code: replay refused
    login_again = other.post("/login/verify", data={"code": now_code(secret, +1)})
    assert login_again.status_code == 302


def test_a_recovery_code_logs_in_once(app, client, alice):
    secret, codes = turn_on(app, client)
    client.post("/logout")
    first = app.test_client()
    login(first)
    assert first.post("/login/verify", data={"code": codes[0].lower()}).status_code == 302
    assert first.get("/bookings/").status_code == 200
    second = app.test_client()
    login(second)
    assert second.post("/login/verify", data={"code": codes[0]}).status_code == 401
    with app.app_context():
        assert RecoveryCode.query.filter(RecoveryCode.used_at.is_not(None)).count() == 1
        assert AuditLog.query.filter_by(event_type="recovery_code_used").count() == 1


def test_unfinished_logins_expire(app, client, alice):
    turn_on(app, client)
    other = app.test_client()
    login(other)
    with other.session_transaction() as session:
        session["2fa_at"] = time.time() - 600
    assert other.get("/login/verify").status_code == 302


def test_next_page_survives_the_second_step(app, client, alice):
    secret, codes = turn_on(app, client)
    client.post("/logout")
    other = app.test_client()
    res = other.post("/login?next=/bookings/", data={"email": ALICE, "password": PASSWORD})
    assert "/login/verify?next=" in res.headers["Location"] and "bookings" in res.headers["Location"]
    done = other.post(res.headers["Location"], data={"code": now_code(secret, +1)})
    assert done.headers["Location"].endswith("/bookings/")
    evil = app.test_client()
    login(evil)
    out = evil.post("/login/verify?next=https://evil.example/", data={"code": codes[0]})
    assert out.status_code == 302
    assert "evil.example" not in out.headers["Location"]


# ---------------- Turning it off and renewing codes ----------------

def test_turning_it_off_needs_password_and_code(app, client, alice):
    secret, _ = turn_on(app, client)
    for data, message in (({"password": "Wrong-password-1", "code": now_code(secret, +1)}, b"current password"),
                          ({"password": PASSWORD, "code": "000000"}, b"not right"),
                          ({"password": PASSWORD, "code": ""}, b"not right")):
        res = client.post("/account/2fa/disable", data=data)
        assert res.status_code == 400 and message in res.data
    with app.app_context():
        assert User.query.one().totp_enabled
        assert AuditLog.query.filter_by(event_type="two_factor_change_failed").count() == 3
    ok = client.post("/account/2fa/disable", data={"password": PASSWORD, "code": now_code(secret, +1)})
    assert ok.status_code == 302
    with app.app_context():
        user = User.query.one()
        assert not user.totp_enabled and user.totp_secret is None and RecoveryCode.query.count() == 0
    client.post("/logout")
    assert "/login/verify" not in login(client).headers["Location"]       # back to password only


def test_new_recovery_codes_replace_the_old_ones(app, client, alice):
    secret, old = turn_on(app, client)
    res = client.post("/account/2fa/recovery", data={"password": PASSWORD, "code": now_code(secret, +1)})
    new = re.findall(r"<li>([A-Z2-9]{5}-[A-Z2-9]{5})</li>", res.get_data(as_text=True))
    assert len(new) == 8 and not set(new) & set(old)
    client.post("/logout")
    other = app.test_client()
    login(other)
    assert other.post("/login/verify", data={"code": old[0]}).status_code == 401


def test_two_factor_changes_need_a_login_and_a_csrf_token():
    assert create_app("testing").test_client().post("/account/2fa/disable").status_code == 302
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    with app.app_context():
        seed_demo_data(days=2)
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        user.totp_secret, user.totp_enabled = RFC_SECRET, True
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    res = client.post("/login", data={"email": ALICE, "password": PASSWORD, "csrf_token": token})
    assert "/login/verify" in res.headers["Location"]
    assert client.post("/login/verify", data={"code": now_code(RFC_SECRET)}).status_code == 400   # no token
    page = client.get("/login/verify").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    assert client.post("/login/verify", data={"code": now_code(RFC_SECRET), "csrf_token": token}).status_code == 302


def test_accounts_without_two_factor_log_in_as_before(app, client, alice):
    res = login(client)
    assert res.status_code == 302 and "/login/verify" not in res.headers["Location"]
    assert b"Turn on two-factor login" in client.get("/account").data


def test_account_page_shows_the_state_and_remaining_codes(app, client, alice):
    secret, codes = turn_on(app, client)
    html = client.get("/account").get_data(as_text=True)
    assert "Two-factor login" in html and "8 unused recovery codes" in html
    assert "Turn on two-factor login" not in html
