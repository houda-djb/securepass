"""baseline: every table as of the passenger and seat features (v2, phases 8-10)

Safe to run on a database that already has some or all of these tables: the application
creates missing tables when it starts, and this migration only adds the ones that are
still missing. That lets one command, `flask db upgrade`, bring ANY database up to date.

Revision ID: 0001
Revises: 
Create Date: 2026-10-26 22:00:00.954229

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)

def upgrade():
    if not _has_table('airports'):
        op.create_table('airports',
        sa.Column('code', sa.String(length=3), nullable=False),
        sa.Column('city', sa.String(length=80), nullable=False),
        sa.Column('country', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('slug', sa.String(length=40), nullable=False),
        sa.Column('blurb', sa.String(length=200), nullable=False),
        sa.Column('featured_rank', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('code'),
        sa.UniqueConstraint('slug')
        )

    if not _has_table('users'):
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('failed_logins', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'admin')", name='ck_user_role'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
        )

    if not _has_table('audit_log'):
        op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=False),
        sa.Column('detail', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('audit_log', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_audit_log_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_audit_log_event_type'), ['event_type'], unique=False)

    if not _has_table('flights'):
        op.create_table('flights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('flight_no', sa.String(length=8), nullable=False),
        sa.Column('origin_code', sa.String(length=3), nullable=False),
        sa.Column('destination_code', sa.String(length=3), nullable=False),
        sa.Column('departs_at', sa.DateTime(), nullable=False),
        sa.Column('arrives_at', sa.DateTime(), nullable=False),
        sa.Column('price_cents', sa.Integer(), nullable=False),
        sa.Column('seats_available', sa.Integer(), nullable=False),
        sa.CheckConstraint('origin_code != destination_code', name='ck_flight_distinct_airports'),
        sa.CheckConstraint('seats_available >= 0', name='ck_flight_seats_not_negative'),
        sa.ForeignKeyConstraint(['destination_code'], ['airports.code'], ),
        sa.ForeignKeyConstraint(['origin_code'], ['airports.code'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('flight_no', 'departs_at', name='uq_flight_no_departure')
        )
        with op.batch_alter_table('flights', schema=None) as batch_op:
            batch_op.create_index('ix_flight_search', ['origin_code', 'destination_code', 'departs_at'], unique=False)

    if not _has_table('bookings'):
        op.create_table('bookings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(length=8), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('flight_id', sa.Integer(), nullable=False),
        sa.Column('passengers', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name='ck_booking_status'),
        sa.CheckConstraint('passengers BETWEEN 1 AND 9', name='ck_booking_passengers'),
        sa.CheckConstraint('total_cents >= 0', name='ck_booking_total'),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference')
        )
        with op.batch_alter_table('bookings', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_bookings_user_id'), ['user_id'], unique=False)

    if not _has_table('passengers'):
        op.create_table('passengers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=40), nullable=False),
        sa.Column('last_name', sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('passengers', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_passengers_booking_id'), ['booking_id'], unique=False)

    if not _has_table('seat_assignments'):
        op.create_table('seat_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('passenger_id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('flight_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=3), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id'], ),
        sa.ForeignKeyConstraint(['passenger_id'], ['passengers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('flight_id', 'label', name='uq_seat_per_flight'),
        sa.UniqueConstraint('passenger_id')
        )
        with op.batch_alter_table('seat_assignments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_seat_assignments_booking_id'), ['booking_id'], unique=False)


def downgrade():
    with op.batch_alter_table('seat_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_seat_assignments_booking_id'))

    op.drop_table('seat_assignments')
    with op.batch_alter_table('passengers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_passengers_booking_id'))

    op.drop_table('passengers')
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_user_id'))

    op.drop_table('bookings')
    with op.batch_alter_table('flights', schema=None) as batch_op:
        batch_op.drop_index('ix_flight_search')

    op.drop_table('flights')
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_event_type'))
        batch_op.drop_index(batch_op.f('ix_audit_log_created_at'))

    op.drop_table('audit_log')
    op.drop_table('users')
    op.drop_table('airports')
