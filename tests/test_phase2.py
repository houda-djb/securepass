from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Airport, Flight


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def search(client, **overrides):
    params = {"origin": "LHR", "destination": "CDG", "departure": day(3),
              "passengers": "1", "search": "1"}
    params.update(overrides)
    return client.get("/flights", query_string=params)


# ---------- Happy paths ----------

def test_search_returns_matching_flights(client):
    res = search(client)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "SP" in html and "London to Paris" in html
    assert "View details" in html


def test_airport_codes_are_case_insensitive(client):
    res = search(client, origin="lhr", destination="cdg")
    assert res.status_code == 200
    assert "London to Paris" in res.get_data(as_text=True)


def test_return_trip_shows_both_legs(client):
    res = search(client, **{"return": day(5)})
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "Outbound" in html and "Return" in html
    assert "Paris to London" in html


def test_no_flights_message_for_unserved_route(client):
    res = search(client, origin="JRO", destination="BCN")
    assert res.status_code == 200
    assert "No flights match" in res.get_data(as_text=True)


def test_prefill_link_shows_no_errors(client):
    res = client.get("/flights?destination=JTR")
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "Please check your search" not in html
    assert 'value="JTR"' in html


def test_seat_filter_hides_flights_that_are_too_full(app, client):
    with app.app_context():
        for flight in Flight.query.filter_by(origin_code="LHR", destination_code="CDG"):
            flight.seats_available = 2
        db.session.commit()
    assert "No flights match" in search(client, passengers="3").get_data(as_text=True)
    assert "London to Paris" in search(client, passengers="2").get_data(as_text=True)


# ---------- Validation (SR3) ----------

@pytest.mark.parametrize("overrides, message", [
    ({"origin": "L1"}, "3-letter airport code"),
    ({"origin": ""}, "3-letter airport code"),
    ({"destination": "LONDON"}, "3-letter airport code"),
    ({"destination": "LHR"}, "must be different"),
    ({"departure": "not-a-date"}, "valid departure date"),
    ({"departure": day(-1)}, "can't be in the past"),
    ({"departure": day(400)}, "up to one year ahead"),
    ({"return": day(1)}, "can't be before the departure"),
    ({"return": "2026-13-45"}, "valid return date"),
    ({"passengers": "0"}, "between 1 and 9"),
    ({"passengers": "10"}, "between 1 and 9"),
    ({"passengers": "abc"}, "between 1 and 9"),
    ({"passengers": "-2"}, "between 1 and 9"),
    ({"origin": "ZZZ"}, "don't fly to or from"),
])
def test_invalid_search_is_rejected_with_a_message(client, overrides, message):
    res = search(client, **overrides)
    assert res.status_code == 400
    assert message in res.get_data(as_text=True).replace("&#39;", "'")


def test_script_in_search_is_escaped(client):
    res = search(client, origin='"><script>alert(1)</script>')
    html = res.get_data(as_text=True)
    assert res.status_code == 400
    assert "<script>alert" not in html


def test_sql_injection_attempt_is_harmless(client):
    res = search(client, origin="' OR 1=1 --")
    assert res.status_code == 400  # rejected by validation, never reaches the database
    res = search(client, passengers="1; DROP TABLE flights")
    assert res.status_code == 400
    assert client.get("/flights/1").status_code == 200  # table still exists


# ---------- Detail page ----------

def test_flight_detail_page(client):
    res = client.get("/flights/1")
    assert res.status_code == 200
    assert b"Log in to book" in res.data


def test_unknown_flight_is_404(client):
    assert client.get("/flights/999999").status_code == 404
    assert client.get("/flights/abc").status_code == 404
    assert client.get("/flights/99999999999999999999").status_code == 404


# ---------- Homepage and data ----------

def test_homepage_featured_cards_come_from_database(client):
    html = client.get("/").get_data(as_text=True)
    cards = html.split('id="destinations"')[1]  # ignore the airport autocomplete list above
    assert cards.index("Tokyo") < cards.index("Santorini") < cards.index("Serengeti")
    assert "/flights?destination=HND" in cards


def test_homepage_works_without_photos(client):
    assert client.get("/").status_code == 200


def test_seats_can_never_go_negative(app):
    with app.app_context():
        db.session.add(Flight(
            flight_no="SP999", origin_code="LHR", destination_code="CDG",
            departs_at=date.today(), arrives_at=date.today(), price_cents=100, seats_available=-1,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_a_flight_cannot_start_and_end_at_the_same_airport(app):
    with app.app_context():
        db.session.add(Flight(
            flight_no="SP998", origin_code="LHR", destination_code="LHR",
            departs_at=date.today(), arrives_at=date.today(), price_cents=100, seats_available=5,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_featured_airports_are_seeded(app):
    with app.app_context():
        codes = [a.code for a in Airport.query.filter(Airport.featured_rank.is_not(None))
                 .order_by(Airport.featured_rank)]
    assert codes == ["HND", "JTR", "JRO"]