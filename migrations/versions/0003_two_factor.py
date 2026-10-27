"""two-factor login: authenticator secret on users, and recovery codes

Adds users.totp_secret, users.totp_enabled and users.last_totp_step, plus the
recovery_codes table. Safe to run if any of them already exist.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 20:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users", schema=None) as batch_op:
        if "totp_secret" not in columns:
            batch_op.add_column(sa.Column("totp_secret", sa.String(length=64), nullable=True))
        if "totp_enabled" not in columns:
            batch_op.add_column(sa.Column("totp_enabled", sa.Boolean(), nullable=False,
                                          server_default=sa.false()))
        if "last_totp_step" not in columns:
            batch_op.add_column(sa.Column("last_totp_step", sa.Integer(), nullable=True))

    if not inspector.has_table("recovery_codes"):
        op.create_table(
            "recovery_codes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("recovery_codes", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_recovery_codes_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("recovery_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recovery_codes_user_id"))
    op.drop_table("recovery_codes")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("last_totp_step")
        batch_op.drop_column("totp_enabled")
        batch_op.drop_column("totp_secret")
