"""countries: the places people can visit, with best months and trip styles

Adds the countries table. Safe to run if the table already exists (the application
creates missing tables when it starts).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 20:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("countries"):
        op.create_table(
            "countries",
            sa.Column("slug", sa.String(length=40), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("blurb", sa.String(length=240), nullable=False),
            sa.Column("why", sa.String(length=160), nullable=False),
            sa.Column("best_months", sa.String(length=40), nullable=False),
            sa.Column("styles", sa.String(length=80), nullable=False),
            sa.PrimaryKeyConstraint("slug"),
            sa.UniqueConstraint("name"),
        )


def downgrade():
    op.drop_table("countries")
