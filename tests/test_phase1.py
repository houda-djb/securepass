def test_home_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Explore the World, Securely." in res.data


def test_navbar_and_auth_links_present(client):
    html = client.get("/").get_data(as_text=True)
    for label in ("Explore Flights", "Featured Destinations", "Log in", "Register"):
        assert label in html
    # Phase 3 will gate these behind roles; they must not be shown to visitors now.
    assert "My Bookings" not in html
    assert ">Admin<" not in html


def test_search_form_fields(client):
    html = client.get("/").get_data(as_text=True)
    for field in ('name="origin"', 'name="destination"', 'name="departure"',
                  'name="return"', 'name="passengers"'):
        assert field in html
    assert 'method="get"' in html


def test_three_featured_destinations(client):
    html = client.get("/").get_data(as_text=True)
    for name in ("Tokyo", "Santorini", "Serengeti"):
        assert name in html


def test_placeholder_routes(client):
    for path in ("/flights", "/login", "/register"):
        assert client.get(path).status_code == 200


def test_404_page_does_not_leak_details(client):
    res = client.get("/does-not-exist")
    assert res.status_code == 404
    assert b"Traceback" not in res.data
    assert b"We can't find that page" in res.data


def test_session_cookie_flags(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_missing_secret_key_is_refused(monkeypatch):
    import pytest
    from config import CONFIGS, Config

    class NoSecret(Config):
        SECRET_KEY = None

    monkeypatch.setitem(CONFIGS, "nosecret", NoSecret)
    from app import create_app
    with pytest.raises(RuntimeError):
        create_app("nosecret")