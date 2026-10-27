from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow() -> datetime:
    """Current UTC time as a plain (naive) datetime, which is how SQLite stores it."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Airport(db.Model):
    __tablename__ = "airports"

    code = db.Column(db.String(3), primary_key=True)  # IATA code, e.g. "LHR"
    city = db.Column(db.String(80), nullable=False)
    country = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(40), unique=True, nullable=False)  # photo file name
    blurb = db.Column(db.String(200), nullable=False, default="")
    # 1, 2, 3... = shown on the homepage in that order; None = not featured.
    featured_rank = db.Column(db.Integer, nullable=True)

    @property
    def label(self) -> str:
        return f"{self.city} ({self.code})"


class Airline(db.Model):
    """The company that operates a flight. Flight numbers keep the SecurePass "SP" prefix
    (the marketing code), exactly like a codeshare: "SP104, operated by Aurora Air"."""

    __tablename__ = "airlines"

    code = db.Column(db.String(2), primary_key=True)  # two letters, e.g. "AU"
    name = db.Column(db.String(60), nullable=False)

    @property
    def css_class(self) -> str:
        return f"carrier-{self.code.lower()}"


class Flight(db.Model):
    __tablename__ = "flights"

    id = db.Column(db.Integer, primary_key=True)
    flight_no = db.Column(db.String(8), nullable=False)
    origin_code = db.Column(db.String(3), db.ForeignKey("airports.code"), nullable=False)
    destination_code = db.Column(db.String(3), db.ForeignKey("airports.code"), nullable=False)
    # Demo simplification: times are stored as plain local times, time zones are ignored.
    departs_at = db.Column(db.DateTime, nullable=False)
    arrives_at = db.Column(db.DateTime, nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)  # money as whole cents, never floats
    seats_available = db.Column(db.Integer, nullable=False)
    # Optional: flights added by an admin may not name an operator.
    airline_code = db.Column(db.String(2), db.ForeignKey("airlines.code"), nullable=True)

    airline = db.relationship("Airline")
    origin = db.relationship("Airport", foreign_keys=[origin_code])
    destination = db.relationship("Airport", foreign_keys=[destination_code])

    __table_args__ = (
        db.CheckConstraint("seats_available >= 0", name="ck_flight_seats_not_negative"),
        db.CheckConstraint("origin_code != destination_code", name="ck_flight_distinct_airports"),
        db.UniqueConstraint("flight_no", "departs_at", name="uq_flight_no_departure"),
        db.Index("ix_flight_search", "origin_code", "destination_code", "departs_at"),
    )

    @property
    def price_display(self) -> str:
        return f"${self.price_cents / 100:,.2f}"

    @property
    def has_departed(self) -> bool:
        # Flight times are plain local times in this demo, so compare with local time.
        return self.departs_at <= datetime.now()

    @property
    def duration_display(self) -> str:
        minutes = int((self.arrives_at - self.departs_at).total_seconds() // 60)
        return f"{minutes // 60}h {minutes % 60:02d}m"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)  # always stored lowercase
    password_hash = db.Column(db.String(255), nullable=False)       # SR1: never the password itself
    role = db.Column(db.String(10), nullable=False, default="user")  # FR4: "user" or "admin"
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Two-factor login with an authenticator app (TOTP). The secret only counts once enabled.
    totp_secret = db.Column(db.String(64), nullable=True)
    totp_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    last_totp_step = db.Column(db.Integer, nullable=True)  # blocks re-using a code (replay)

    __table_args__ = (db.CheckConstraint("role IN ('user', 'admin')", name="ck_user_role"),)

    def set_password(self, password: str) -> None:
        # Werkzeug's default is scrypt with a random salt per password.
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_locked(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.locked_until is not None and self.locked_until > now

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class AuditLog(db.Model):
    """SR13: security-relevant events. Phase 5 turns this into the security dashboard."""

    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    ip = db.Column(db.String(45), nullable=False, default="")
    detail = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)


class Booking(db.Model):
    """A reservation of seats on one flight by one user (FR9-FR12)."""

    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    # FR10: random public code like "K7M2QX9P". The numeric id is never shown to users.
    reference = db.Column(db.String(8), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    flight_id = db.Column(db.Integer, db.ForeignKey("flights.id"), nullable=False)
    passengers = db.Column(db.Integer, nullable=False)
    total_cents = db.Column(db.Integer, nullable=False)  # worked out on the server, never sent by the browser
    status = db.Column(db.String(10), nullable=False, default="confirmed")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    flight = db.relationship("Flight")
    # The people travelling (names only). `passengers` above is just their count.
    travellers = db.relationship("Passenger", back_populates="booking",
                                 order_by="Passenger.position", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("passengers BETWEEN 1 AND 9", name="ck_booking_passengers"),
        db.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_booking_status"),
        db.CheckConstraint("total_cents >= 0", name="ck_booking_total"),
    )

    @property
    def total_display(self) -> str:
        return f"${self.total_cents / 100:,.2f}"

    @property
    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    @property
    def can_cancel(self) -> bool:
        return self.status == "confirmed" and not self.flight.has_departed


class Passenger(db.Model):
    """One traveller on a booking. Names only: no passport or card data is ever stored."""

    __tablename__ = "passengers"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)  # 1 = lead passenger
    first_name = db.Column(db.String(40), nullable=False)
    last_name = db.Column(db.String(40), nullable=False)

    booking = db.relationship("Booking", back_populates="travellers")
    seat = db.relationship("SeatAssignment", back_populates="passenger", uselist=False,
                           cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"



class SeatAssignment(db.Model):
    """The seat one passenger has chosen on a flight (for example "12A")."""

    __tablename__ = "seat_assignments"

    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey("passengers.id"), unique=True, nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True)
    flight_id = db.Column(db.Integer, db.ForeignKey("flights.id"), nullable=False)
    label = db.Column(db.String(3), nullable=False)

    passenger = db.relationship("Passenger", back_populates="seat")

    # The database itself refuses to give one seat to two people, even in a race (NFR5).
    __table_args__ = (db.UniqueConstraint("flight_id", "label", name="uq_seat_per_flight"),)



class RecoveryCode(db.Model):
    """One-time codes for logging in when the authenticator app is lost. Only a keyed hash
    is stored, so the codes themselves can't be read back from the database."""

    __tablename__ = "recovery_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
