"""Phase 27: the new look and the signed-in dashboard on the home page."""
from tests.test_phase10 import a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with


def test_visitors_do_not_see_the_dashboard(client):
    assert "Your dashboard" not in client.get("/").get_data(as_text=True)


def test_dashboard_shows_the_next_trip(app, client, users):
    login(client)
    page = client.get("/").get_data(as_text=True)
    assert "Your dashboard" in page and "No upcoming trip yet." in page
    book_with(client, a_flight(app))
    page = client.get("/").get_data(as_text=True)
    assert "Live updates" in page and "On time" in page and "Verified profile" in page


def test_dashboard_is_translated(client, users):
    login(client)
    client.post("/language", data={"lang": "fr"})
    assert "Votre tableau de bord" in client.get("/").get_data(as_text=True)


def test_new_theme_files_are_served(client):
    css = client.get("/static/css/style.css").get_data(as_text=True)
    assert "Theme v4" in css and "backdrop-filter" in css
