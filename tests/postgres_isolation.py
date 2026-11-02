"""Gives every test an empty PostgreSQL database, so the whole suite can run on PostgreSQL.

Used only when TEST_DATABASE_URL is set (CI does this):
    pytest -p tests.postgres_isolation
Without TEST_DATABASE_URL it does nothing, so normal runs stay on in-memory SQLite.
"""
import os

import psycopg
import pytest

URL = os.environ.get("TEST_DATABASE_URL", "").strip()


def wipe() -> None:
    with psycopg.connect(URL.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        connection.execute("CREATE SCHEMA public")


@pytest.fixture(autouse=True)
def empty_postgres_database():
    if URL:
        wipe()
    yield
