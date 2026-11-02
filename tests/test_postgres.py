"""Checks that only make sense on a real PostgreSQL server.

They run when TEST_DATABASE_URL points to PostgreSQL (CI does this) and are skipped otherwise:
    TEST_DATABASE_URL=postgresql://user:pass@localhost/db pytest -p tests.postgres_isolation
"""
import os
from datetime import datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import Airport, Flight

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgres"),
                                reason="needs PostgreSQL: set TEST_DATABASE_URL")

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


@pytest.fixture()
def empty_app():
    """An app on an empty PostgreSQL database: no tables yet, migrations must build them."""
    app = create_app("testing", {"AUTO_CREATE_TABLES": False})
    yield app
    with app.app_context():
        db.engine.dispose()


def test_the_tests_really_run_on_postgresql(empty_app):
    with empty_app.app_context():
        assert db.engine.dialect.name == "postgresql"


def test_migrations_build_exactly_the_schema_the_models_describe_on_postgresql(empty_app):
    with empty_app.app_context():
        upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
            newest = ScriptDirectory(MIGRATIONS).get_current_head()
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == newest


def test_migrations_work_on_a_database_the_app_created_itself_on_postgresql():
    app = create_app("testing")          # create_all runs, as it does on a first start
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        upgrade(directory=MIGRATIONS)    # and running it again changes nothing
        db.engine.dispose()


def test_a_migration_can_be_undone_and_redone_on_postgresql(empty_app):
    with empty_app.app_context():
        upgrade(directory=MIGRATIONS)
        downgrade(directory=MIGRATIONS, revision="0001")
        with db.engine.connect() as connection:
            tables = set(connection.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).scalars())
        assert "airlines" not in tables and "flights" in tables
        upgrade(directory=MIGRATIONS)


def test_database_refuses_two_flights_with_the_same_number_and_time(app):
    with app.app_context():
        first = Flight.query.first()
        db.session.add(Flight(flight_no=first.flight_no, origin_code=first.origin_code,
                              destination_code=first.destination_code, departs_at=first.departs_at,
                              arrives_at=first.arrives_at, price_cents=100, seats_available=1))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_database_refuses_a_flight_to_an_unknown_airport(app):
    with app.app_context():
        db.session.add(Flight(flight_no="SP999", origin_code="LHR", destination_code="ZZZ",
                              departs_at=datetime(2031, 1, 1, 8), arrives_at=datetime(2031, 1, 1, 9),
                              price_cents=100, seats_available=1))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_text_and_dates_survive_a_round_trip_on_postgresql(app):
    with app.app_context():
        flight = Flight.query.order_by(Flight.id).first()
        airport = db.session.get(Airport, flight.origin_code)
        assert isinstance(flight.departs_at, datetime) and flight.price_cents > 0
        assert airport.city
