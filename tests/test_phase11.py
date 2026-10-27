from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import Airline, Booking, Flight, User
from app.seed import AIRLINES

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = str(ROOT / "migrations")
PASSWORD = "Correct-horse-42"


def day_flights(app, origin="LHR", destination="CDG", offset=5):
    start = datetime.combine(date.today() + timedelta(days=offset), time.min)
    with app.app_context():
        return Flight.query.filter(Flight.origin_code == origin, Flight.destination_code == destination,
                                   Flight.departs_at >= start,
                                   Flight.departs_at < start + timedelta(days=1)).all()


def search(client, offset=5, origin="LHR", destination="CDG"):
    day = (date.today() + timedelta(days=offset)).isoformat()
    return client.get("/flights", query_string={"origin": origin, "destination": destination,
                                                "departure": day, "passengers": "1", "search": "1"})


# ---------------- Airlines in the demo data ----------------

def test_demo_data_has_five_airlines_and_every_flight_has_one(app):
    with app.app_context():
        assert {a.code: a.name for a in Airline.query} == dict(AIRLINES)
        assert Flight.query.filter(Flight.airline_code.is_(None)).count() == 0


def test_both_directions_of_a_route_use_the_same_airline(app):
    with app.app_context():
        pair = {(f.origin_code, f.destination_code): f.airline_code for f in Flight.query.all()}
        assert pair[("JFK", "LHR")] == pair[("LHR", "JFK")]


def test_flight_numbers_keep_the_securepass_prefix(app):
    with app.app_context():
        assert all(f.flight_no.startswith("SP") for f in Flight.query.limit(200))


# ---------------- Pages ----------------

def test_search_results_name_the_operator(app, client):
    flight = day_flights(app)[0]
    with app.app_context():
        name = db.session.get(Flight, flight.id).airline.name
        code = flight.airline_code
    html = search(client).get_data(as_text=True)
    assert f"Operated by {name}" in html and f'data-airline="{code}"' in html
    assert f"carrier-{code.lower()}" in html and "SP104" in html


def test_flight_detail_names_the_operator(app, client):
    flight = day_flights(app)[0]
    with app.app_context():
        name = db.session.get(Flight, flight.id).airline.name
    assert f"Operated by {name}" in client.get(f"/flights/{flight.id}").get_data(as_text=True)


def test_booking_page_names_the_operator(app, client):
    with app.app_context():
        user = User(email="alice@example.com", role="user")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    client.post("/login", data={"email": "alice@example.com", "password": PASSWORD})
    flight = day_flights(app)[0]
    res = client.post(f"/bookings/new/{flight.id}", data={"passengers": "1"})
    with app.app_context():
        name = db.session.get(Flight, flight.id).airline.name
    assert f"Operated by {name}" in client.get(res.headers["Location"]).get_data(as_text=True)


def test_a_flight_without_an_airline_still_works(app, client):
    with app.app_context():
        flight = db.session.get(Flight, day_flights(app)[0].id)
        flight.airline_code = None
        db.session.commit()
        fid = flight.id
    html = search(client).get_data(as_text=True)
    assert "Operated by" not in html and 'data-airline=""' in html and "SP104" in html
    assert client.get(f"/flights/{fid}").status_code == 200


def test_the_airline_filter_appears_only_when_results_have_several_airlines(app, client):
    assert "Airlines</legend>" not in search(client).get_data(as_text=True)      # one carrier: nothing to filter
    existing = day_flights(app)[0]
    with app.app_context():
        other = next(code for code, _ in AIRLINES if code != existing.airline_code)
        db.session.add(Flight(flight_no="SP900", origin_code="LHR", destination_code="CDG",
                              departs_at=existing.departs_at + timedelta(hours=5),
                              arrives_at=existing.arrives_at + timedelta(hours=5),
                              price_cents=9900, seats_available=50, airline_code=other))
        db.session.commit()
    html = search(client).get_data(as_text=True)
    assert "Airlines</legend>" in html and html.count("data-airline-filter") == 2


def test_removing_an_airline_in_use_is_blocked_by_the_database(app):
    from sqlalchemy.exc import IntegrityError
    with app.app_context():
        db.session.execute(text("PRAGMA foreign_keys=ON"))
        used = Flight.query.first().airline_code
        try:
            db.session.execute(text("DELETE FROM airlines WHERE code = :c"), {"c": used})
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            pytest.skip("SQLite foreign key enforcement is off in this configuration")


# ---------------- Database migrations ----------------

def migration_app(tmp_path, **config):
    return create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}",
                                  "AUTO_CREATE_TABLES": False, **config})


def test_migrations_build_exactly_the_schema_the_models_describe(tmp_path):
    app = migration_app(tmp_path)
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), db.metadata)
        db.engine.dispose()
    assert differences == []


def test_an_older_database_gets_airlines_without_losing_flights(tmp_path):
    app = migration_app(tmp_path)
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="0001")          # the schema before airlines existed
        with db.engine.begin() as connection:
            connection.execute(text("INSERT INTO airports (code, city, country, name, slug, blurb) VALUES "
                                    "('LHR','London','UK','Heathrow','london',''),('CDG','Paris','FR','CDG','paris','')"))
            for number, day in (("SP100", "01"), ("SP102", "02"), ("SP119", "03"), ("XY777", "04")):
                connection.execute(text(
                    "INSERT INTO flights (flight_no, origin_code, destination_code, departs_at, arrives_at, "
                    "price_cents, seats_available) VALUES (:n, 'LHR', 'CDG', :d, :a, 100, 5)"),
                    {"n": number, "d": f"2030-01-{day} 08:00", "a": f"2030-01-{day} 09:00"})
        upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            rows = dict(connection.execute(text("SELECT flight_no, airline_code FROM flights")).all())
            airlines = connection.execute(text("SELECT count(*) FROM airlines")).scalar()
        db.engine.dispose()
    assert rows == {"SP100": "AU", "SP102": "NB", "SP119": "VT", "XY777": None}
    assert airlines == 5


def test_migrations_also_work_on_a_database_the_app_created_itself(tmp_path):
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}"})   # create_all ran
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            newest = ScriptDirectory(MIGRATIONS).get_current_head()
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == newest
        db.engine.dispose()


def test_a_migration_can_be_undone_and_redone(tmp_path):
    app = migration_app(tmp_path)
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        downgrade(directory=MIGRATIONS, revision="0001")   # undoes 0003 and 0002
        with db.engine.connect() as connection:
            tables = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars())
        assert "airlines" not in tables and "flights" in tables
        upgrade(directory=MIGRATIONS)
        db.engine.dispose()
