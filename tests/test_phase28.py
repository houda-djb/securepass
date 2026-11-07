"""Phase 28: the home page as an app shell (icon bar, hero scene, pill search, dashboard panel)."""
from tests.test_phase10 import login, users  # noqa: F401


def test_home_has_the_new_layout(client):
    page = client.get("/").get_data(as_text=True)
    for part in ("class=\"rail\"", "hero-card", "hero-search", "Book your next adventure securely",
                 "Discover", "side-panel", "Where to next from Alger?"):
        assert part in page
    assert "Your dashboard" not in page and "SecurePass" in page


def test_search_still_works_from_the_pill(client):
    page = client.get("/").get_data(as_text=True)
    assert 'name="origin"' in page and 'name="destination"' in page and "Search available flights" in page


def test_signed_in_panel_and_french(client, users):
    login(client)
    assert "Your dashboard" in client.get("/").get_data(as_text=True)
    client.post("/language", data={"lang": "fr"})
    page = client.get("/").get_data(as_text=True)
    assert "Réservez votre prochaine aventure en toute sécurité" in page and "Découvrir" in page


def test_hero_scene_and_theme_v5_are_served(client):
    assert client.get("/static/img/hero-scene.svg").status_code == 200
    assert "Theme v5" in client.get("/static/css/style.css").get_data(as_text=True)


def test_home_keeps_the_top_trips_label(client):
    assert "Top trips from" in client.get("/").get_data(as_text=True)


def test_departures_board_lists_real_flights(client, app):
    page = client.get("/").get_data(as_text=True)
    assert "Departures from Alger" in page and "board-table" in page and "data-clock" in page


def test_board_is_translated(client):
    client.post("/language", data={"lang": "fr"})
    assert "Départs d&#39;Alger" in client.get("/").get_data(as_text=True) or "Départs d'Alger" in client.get("/").get_data(as_text=True)


def test_hero_photo_is_a_real_jpeg(client):
    r = client.get("/static/img/destinations/hero.jpg")
    assert r.status_code == 200 and r.data[:3] == b"\xff\xd8\xff"
