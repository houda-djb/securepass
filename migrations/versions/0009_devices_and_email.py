"""confirmed email address and the list of signed-in devices

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-15 18:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "email_verified_at" not in {c["name"] for c in inspector.get_columns("users")}:  # safe to run twice
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("email_verified_at", sa.DateTime(), nullable=True))
        # Accounts that already exist keep working: they count as confirmed.
        op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")
    if "user_sessions" not in inspector.get_table_names():
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("sid", sa.String(64), nullable=False, unique=True),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("user_agent", sa.String(200), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])


def downgrade():
    op.drop_table("user_sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified_at")
