"""session epoch: lets a user log out of every device at once

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14 21:40:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "session_epoch" not in columns:  # safe to run twice
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("session_epoch")
