"""cancellation trace: the reason and the network address of every cancellation

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("bookings")}
    with op.batch_alter_table("bookings") as batch:
        if "cancel_reason" not in columns:
            batch.add_column(sa.Column("cancel_reason", sa.String(length=20), nullable=True))
        if "cancelled_ip" not in columns:
            batch.add_column(sa.Column("cancelled_ip", sa.String(length=45), nullable=True))


def downgrade():
    with op.batch_alter_table("bookings") as batch:
        batch.drop_column("cancelled_ip")
        batch.drop_column("cancel_reason")
