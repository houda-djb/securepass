import re
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, User
from app.seed import seed_demo_data

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Correct-horse-42"
ALICE, ADMIN = "alice@example.com", "admin@example.com"
STRONG_KEY = "k" * 48


@pytest.fixture()
def users(app):
    with app.app_context():
        for email, role in ((ALICE, "user"), (ADMIN, "admin")):
            user = User(email=email, role=role)
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.commit()


def login(client, email=ALICE):
    return client.post("/login", data={"email": email, "password": PASSWORD})


def csp_of(response) -> dict:
    policy = {}
    for part in response.headers["Content-Security-Policy"].split(";"):
        name, *values = part.split()
        policy[name] = values
    return policy


def production_app(**overrides):
    config = {"SECRET_KEY": STRONG_KEY, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
              "RATELIMIT_ENABLED": False}
    config.update(overrides)
    app = create_app("production", config)
    with app.app_context():
        seed_demo_data(days=3)
        user = User(email=ALICE, role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    return app


# ---------------- Security headers on every kind of page (SR9) ----------------

@pytest.mark.parametrize("path", ["/", "/login", "/register", "/flights", "/does-not-exist",
                                  "/static/css/style.css"])
def test_security_headers_are_on_every_response(client, path):
    res = client.get(path)
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in res.headers["Permissions-Policy"]
    assert res.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert res.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "Content-Security-Policy" in res.headers


def test_error_pages_carry_the_headers_too(app, client, users):
    login(client)
    forbidden = client.get("/admin/")
    assert forbidden.status_code == 403 and "Content-Security-Policy" in forbidden.headers


def test_csp_only_allows_this_site(client):
    csp = csp_of(client.get("/"))
    assert csp["default-src"] == ["'self'"]
    assert csp["script-src"] == ["'self'"]                        # no inline script, no other site
    assert csp["style-src"] == ["'self'"]
    assert csp["font-src"] == ["'self'"]
    assert csp["img-src"] == ["'self'"]
    assert csp["object-src"] == ["'none'"]
    assert csp["base-uri"] == ["'self'"] and csp["form-action"] == ["'self'"]
    assert csp["frame-ancestors"] == ["'none'"]
    assert "'unsafe-inline'" not in client.get("/").headers["Content-Security-Policy"]
    assert "'unsafe-eval'" not in client.get("/").headers["Content-Security-Policy"]


def test_templates_work_with_the_strict_csp():
    """No inline script, inline style or inline event handler, which the CSP would block."""
    for template in (ROOT / "app" / "templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        name = template.relative_to(ROOT)
        assert not re.search(r"<script\b(?![^>]*\bsrc=)", text), f"{name}: inline <script>"
        assert not re.search(r"\sstyle\s*=", text), f"{name}: style attribute"
        assert not re.search(r"\son[a-z]+\s*=", text), f"{name}: inline event handler"
        assert "javascript:" not in text, f"{name}: javascript: link"


def test_templates_load_nothing_from_unexpected_sites():
    allowed = set()  # since v2 the Inter font is self-hosted, so nothing loads from other sites
    for template in (ROOT / "app" / "templates").rglob("*.html"):
        for host in re.findall(r"https?://([^/\"'\s]+)", template.read_text(encoding="utf-8")):
            assert host in allowed, f"{template.name} loads from {host}"


# ---------------- HTTPS and production settings (SR8, SR9, SR11) ----------------

def test_development_does_not_force_https_or_send_hsts(client):
    res = client.get("/")
    assert res.status_code == 200 and "Strict-Transport-Security" not in res.headers


def test_production_redirects_http_to_https():
    client = production_app().test_client()
    res = client.get("/login", base_url="http://localhost")
    assert res.status_code in (301, 302)
    assert res.headers["Location"] == "https://localhost/login"


def test_production_sends_hsts_over_https():
    client = production_app().test_client()
    hsts = client.get("/", base_url="https://localhost").headers["Strict-Transport-Security"]
    assert "max-age=31536000" in hsts and "includeSubDomains" in hsts


def test_production_session_cookie_is_locked_down():
    app = production_app(WTF_CSRF_ENABLED=False)
    client = app.test_client()
    res = client.post("/login", data={"email": ALICE, "password": PASSWORD},
                      base_url="https://localhost")
    cookie = next(c for c in res.headers.getlist("Set-Cookie") if c.startswith("__Host-session="))
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Path=/" in cookie and "Domain" not in cookie       # what the __Host- prefix demands


def test_production_never_runs_in_debug_mode():
    assert production_app().debug is False


@pytest.mark.parametrize("key", ["short", "x" * 31])
def test_production_refuses_a_weak_secret_key(key):
    with pytest.raises(RuntimeError, match="at least 32"):
        create_app("production", {"SECRET_KEY": key, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def test_production_refuses_to_start_without_a_secret_key():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production", {"SECRET_KEY": None, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def test_proxy_hops_must_be_a_sensible_number(monkeypatch):
    import config

    monkeypatch.setenv("PROXY_HOPS", "lots")
    with pytest.raises(RuntimeError, match="whole number"):
        config._env_int("PROXY_HOPS", 0, maximum=5)
    monkeypatch.setenv("PROXY_HOPS", "99")
    with pytest.raises(RuntimeError, match="between 0 and 5"):
        config._env_int("PROXY_HOPS", 0, maximum=5)
    monkeypatch.setenv("PROXY_HOPS", "2")
    assert config._env_int("PROXY_HOPS", 0, maximum=5) == 2
    monkeypatch.delenv("PROXY_HOPS")
    assert config._env_int("PROXY_HOPS", 0, maximum=5) == 0


# ---------------- Real client address behind a proxy ----------------

def failed_login_ip(app, forwarded_for):
    client = app.test_client()
    client.post("/login", data={"email": "nobody@example.com", "password": PASSWORD},
                headers={"X-Forwarded-For": forwarded_for}, environ_base={"REMOTE_ADDR": "10.0.0.1"})
    with app.app_context():
        return AuditLog.query.filter_by(event_type="login_failed").one().ip


def test_forwarded_addresses_are_ignored_unless_a_proxy_is_configured():
    # A visitor who invents an X-Forwarded-For header must not be able to hide behind it.
    assert failed_login_ip(create_app("testing"), "203.0.113.5") == "10.0.0.1"


def test_forwarded_address_is_used_when_one_proxy_is_configured():
    assert failed_login_ip(create_app("testing", {"PROXY_HOPS": 1}), "203.0.113.5") == "203.0.113.5"


# ---------------- Private pages are not cached ----------------

def test_login_and_account_pages_are_never_cached(client, users):
    assert client.get("/login").headers["Cache-Control"] == "no-store"
    login(client)
    for path in ("/", "/flights", "/bookings/"):
        assert client.get(path).headers["Cache-Control"] == "no-store", path


def test_admin_pages_are_never_cached(client, users):
    login(client, ADMIN)
    assert client.get("/admin/").headers["Cache-Control"] == "no-store"


def test_public_pages_and_static_files_stay_cacheable(client):
    assert "no-store" not in client.get("/").headers.get("Cache-Control", "")
    assert "no-store" not in client.get("/static/css/style.css").headers.get("Cache-Control", "")


# ---------------- Error handling that never leaks (SR12) ----------------

def test_an_unexpected_error_shows_a_safe_500_page():
    app = create_app("testing", {"PROPAGATE_EXCEPTIONS": False})

    @app.route("/boom")
    def boom():
        return 1 / 0

    res = app.test_client().get("/boom")
    body = res.get_data(as_text=True)
    assert res.status_code == 500 and "Something went wrong" in body
    for secret in ("Traceback", "ZeroDivisionError", "division by zero", ".py", "line "):
        assert secret not in body


def test_missing_csrf_token_gets_a_friendly_400_page():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    res = app.test_client().post("/login", data={"email": ALICE, "password": PASSWORD})
    body = res.get_data(as_text=True)
    assert res.status_code == 400
    assert "couldn't process" in body
    assert "CSRF" not in body


def test_oversized_requests_are_refused(client):
    res = client.post("/login", data={"email": "a" * 300_000, "password": PASSWORD})
    assert res.status_code == 413 and b"too large" in res.data


# ---------------- Acceptance criterion AC7 and requirement NFR4 ----------------

def test_a_failed_login_shows_up_on_the_security_dashboard(app, users):
    visitor = app.test_client()
    assert login(visitor, ALICE).status_code == 302
    visitor.post("/logout")
    assert visitor.post("/login", data={"email": ALICE, "password": "Wrong-password-1"}).status_code == 401

    boss = app.test_client()
    login(boss, ADMIN)
    html = boss.get("/admin/").get_data(as_text=True)
    assert "login failed" in html and "failed attempt 1" in html and ALICE in html
    with app.app_context():
        from app.admin.queries import dashboard_stats
        assert dashboard_stats()["failed_logins"] == 1


def test_search_stays_fast_with_three_months_of_flights():
    app = create_app("testing")
    with app.app_context():
        seed_demo_data(days=90)
    client = app.test_client()
    day = (date.today() + timedelta(days=30)).isoformat()
    started = time.perf_counter()
    res = client.get("/flights", query_string={"origin": "LHR", "destination": "CDG",
                                               "departure": day, "passengers": "1", "search": "1"})
    elapsed = time.perf_counter() - started
    assert res.status_code == 200 and b"London to Paris" in res.data
    assert elapsed < 2.0, f"search took {elapsed:.2f}s"