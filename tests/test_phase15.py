"""Phase 15: every pair of airports has flights, and seeding can be repeated safely."""
from datetime import date, timedelta
from itertools import permutations

from app.extensions import db
from app.models import Airport, Flight
from app.seed import seed_demo_data


def test_every_pair_of_airports_has_a_flight(app):
    from app.seed import AIRPORTS, DOMESTIC, HUB
    with app.app_context():
        original = [a[0] for a in AIRPORTS[:10]]
        pairs = set(permutations(original, 2))
        for code in (a[0] for a in AIRPORTS):
            if code != HUB:
                pairs |= {(HUB, code), (code, HUB)}
        pairs |= set(permutations([HUB] + DOMESTIC, 2))
        for origin, destination in pairs:
            assert Flight.query.filter_by(origin_code=origin, destination_code=destination).first(), \
                f"no flight {origin} to {destination}"


def test_istanbul_to_tokyo_can_be_searched(client):
    day = date.today() + timedelta(days=3)
    res = client.get(f"/flights?search=1&origin=IST&destination=HND&departure={day}&passengers=1")
    assert res.status_code == 200
    assert "No flights match" not in res.get_data(as_text=True)


def test_seeding_twice_adds_nothing(app):
    with app.app_context():
        seed_demo_data(days=30)          # first top up whatever the test fixture left out
        before = Flight.query.count()
        assert seed_demo_data(days=30) == 0
        assert Flight.query.count() == before


def test_seeding_tops_up_later_days(app):
    with app.app_context():
        seed_demo_data(days=30)
        before = Flight.query.count()
        assert seed_demo_data(days=40) > 0
        assert Flight.query.count() > before


def test_generated_flights_are_sensible(app):
    with app.app_context():
        for flight in Flight.query.limit(3000):
            assert flight.arrives_at > flight.departs_at
            assert flight.price_cents >= 3500
            assert 1 <= len(flight.flight_no) - 2 <= 4
