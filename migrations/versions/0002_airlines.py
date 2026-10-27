"""airlines: who operates each flight

Adds the airlines table and the optional flights.airline_code column. Safe to run on a
database that already has either one. Existing demo flights (SP100 to SP125) are given the
same carrier the seed data would give them, so an older database looks like a fresh one.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26 22:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

AIRLINES = [
    ("AU", "Aurora Air"),
    ("NB", "Nimbus Airways"),
    ("MJ", "Meridian Jet"),
    ("SL", "Solstice Air"),
    ("VT", "Vantage Airlines"),
]


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("airlines"):
        op.create_table(
            "airlines",
            sa.Column("code", sa.String(length=2), nullable=False),
            sa.Column("name", sa.String(length=60), nullable=False),
            sa.PrimaryKeyConstraint("code"),
        )

    columns = {column["name"] for column in inspector.get_columns("flights")}
    if "airline_code" not in columns:
        with op.batch_alter_table("flights", schema=None) as batch_op:
            batch_op.add_column(sa.Column("airline_code", sa.String(length=2), nullable=True))
            batch_op.create_foreign_key("fk_flights_airline_code", "airlines", ["airline_code"], ["code"])

    connection = op.get_bind()
    has_demo_flights = connection.execute(sa.text("SELECT 1 FROM flights LIMIT 1")).first()
    if has_demo_flights:
        known = {row[0] for row in connection.execute(sa.text("SELECT code FROM airlines"))}
        for code, name in AIRLINES:
            if code not in known:
                connection.execute(sa.text("INSERT INTO airlines (code, name) VALUES (:c, :n)"),
                                   {"c": code, "n": name})
        rows = connection.execute(sa.text(
            "SELECT id, flight_no FROM flights WHERE airline_code IS NULL AND flight_no LIKE 'SP1__'")).all()
        for flight_id, flight_no in rows:
            route_index = (int(flight_no[2:]) - 100) // 2   # SP100/SP101 = route 0, and so on
            connection.execute(sa.text("UPDATE flights SET airline_code = :c WHERE id = :i"),
                               {"c": AIRLINES[route_index % len(AIRLINES)][0], "i": flight_id})


def downgrade():
    with op.batch_alter_table("flights", schema=None) as batch_op:
        batch_op.drop_constraint("fk_flights_airline_code", type_="foreignkey")
        batch_op.drop_column("airline_code")
    op.drop_table("airlines")
