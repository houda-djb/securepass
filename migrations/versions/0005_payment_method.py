"""payment method: which demo payment option a booking used

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04 14:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("bookings")}
    if "payment_method" not in columns:
        with op.batch_alter_table("bookings") as batch:
            batch.add_column(sa.Column("payment_method", sa.String(length=12), nullable=False,
                                       server_default="card"))


def downgrade():
    with op.batch_alter_table("bookings") as batch:
        batch.drop_column("payment_method")
