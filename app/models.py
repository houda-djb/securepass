from app.extensions import db


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
    def duration_display(self) -> str:
        minutes = int((self.arrives_at - self.departs_at).total_seconds() // 60)
        return f"{minutes // 60}h {minutes % 60:02d}m"