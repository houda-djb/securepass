"""seat holds: seats kept for a traveller for 15 minutes during checkout

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-07 20:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    if "seat_holds" in sa.inspect(op.get_bind()).get_table_names():
        return  # safe to run twice
    op.create_table(
        "seat_holds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("flight_id", sa.Integer(), sa.ForeignKey("flights.id"), nullable=False),
        sa.Column("passengers", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("passengers BETWEEN 1 AND 9", name="ck_hold_passengers"),
    )
    op.create_index("ix_seat_holds_flight_id", "seat_holds", ["flight_id"])
    op.create_index("ix_seat_holds_expires_at", "seat_holds", ["expires_at"])


def downgrade():
    op.drop_table("seat_holds")
