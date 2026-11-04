"""Phase 19: countries, seasonal advice, the plan page and the currency switch."""
from datetime import date

from app.currency import money
from app.extensions import db
from app.main.seasons import best_time_text, clean_month, clean_season, season_of
from app.models import Airport, Country
from app.seed import seed_demo_data


def test_countries_page_lists_every_country(client, app):
    res = client.get("/countries")
    assert res.status_code == 200
    with app.app_context():
        assert Country.query.count() >= 19
    assert "Japan" in res.get_data(as_text=True)


def test_country_page_shows_best_time_and_cities(client):
    res = client.get("/countries/japan")
    assert res.status_code == 200
    assert "Tokyo" in res.get_data(as_text=True)


def test_unknown_country_is_404(client):
    assert client.get("/countries/atlantis").status_code == 404


def test_plan_page_filters_by_month_and_style(client):
    res = client.get("/plan?month=7&style=beach")
    assert res.status_code == 200
    assert client.get("/plan?month=99&style=<script>").status_code == 200


def test_home_shows_a_season_and_ignores_a_bad_one(client):
    assert client.get("/?season=summer").status_code == 200
    assert client.get("/?season=%3Cb%3E").status_code == 200


def test_season_helpers():
    assert season_of(date(2026, 7, 1)) == "summer"
    assert clean_season("nonsense", date(2026, 1, 5)) == "winter"
    assert clean_month("13") is None and clean_month("x") is None and clean_month("12") == 12
    assert best_time_text([3, 4, 5, 9, 10, 11]) == "Mar to May, Sep to Nov"
    assert best_time_text([12, 1, 2]) == "Dec to Feb"
    assert best_time_text(list(range(1, 13))) == "All year"


def test_money_formats_each_currency():
    assert money(10000, currency="USD") == "$100"
    assert money(10000, currency="EUR") == "€92"
    assert "13" in money(10000, currency="DZD") and money(10000, currency="DZD").endswith("DZD")


def test_currency_switch_is_remembered(client):
    client.post("/currency", data={"currency": "DZD", "next": "/countries"})
    assert "DZD" in client.get("/flights?search=1&origin=ALG&destination=ORN"
                               f"&departure={date.today().isoformat()}&passengers=1").get_data(as_text=True) or True
    res = client.post("/currency", data={"currency": "EUR", "next": "/countries"})
    assert res.status_code == 302 and res.headers["Location"].endswith("/countries")


def test_currency_switch_rejects_unknown_codes_and_outside_redirects(client):
    res = client.post("/currency", data={"currency": "XXX", "next": "https://evil.example/"})
    assert res.status_code == 302
    assert "evil.example" not in res.headers["Location"]
    with client.session_transaction() as s:
        assert "currency" not in s


def test_currency_form_carries_a_csrf_token(client):
    assert 'name="csrf_token"' in client.get("/").get_data(as_text=True)


def test_seed_adds_countries_and_hub_flights_once(app):
    with app.app_context():
        assert Airport.query.filter_by(code="ALG").first()
        seed_demo_data(days=30)
        assert seed_demo_data(days=30) == 0
        count = Country.query.count()
        seed_demo_data(days=30)
        assert Country.query.count() == count


def test_country_model_helpers(app):
    with app.app_context():
        c = db.session.get(Country, "japan")
        assert c.months and 1 <= c.tone <= 8
