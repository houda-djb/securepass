"""Demo data: airports and a daily flight on every route for the next N days.

Everything is deterministic (no randomness) so the demo behaves the same every time.
"""
from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select

from app.extensions import db
from app.models import Airline, Airport, Flight

# code, city, country, airport name, slug (photo file), blurb, featured_rank
AIRPORTS = [
    ("HND", "Tokyo", "Japan", "Haneda", "tokyo",
     "Late-night food, quiet shrines and the busiest crossing on earth.", 1),
    ("JTR", "Santorini", "Greece", "Santorini (Thira)", "santorini",
     "White-washed villages on a volcanic rim above the Aegean.", 2),
    ("JRO", "Serengeti", "Tanzania", "Kilimanjaro International", "serengeti",
     "Open plains, big herds and sunrise game drives. Fly into Kilimanjaro.", 3),
    ("JFK", "New York", "United States", "John F. Kennedy International", "new-york", "", None),
    ("LHR", "London", "United Kingdom", "Heathrow", "london", "", None),
    ("CDG", "Paris", "France", "Charles de Gaulle", "paris", "", None),
    ("DXB", "Dubai", "United Arab Emirates", "Dubai International", "dubai", "", None),
    ("FCO", "Rome", "Italy", "Fiumicino", "rome", "", None),
    ("IST", "Istanbul", "Turkey", "Istanbul Airport", "istanbul", "", None),
    ("BCN", "Barcelona", "Spain", "El Prat", "barcelona", "", None),
]

# Fictional carriers that operate the demo routes (code, name).
AIRLINES = [
    ("AU", "Aurora Air"),
    ("NB", "Nimbus Airways"),
    ("MJ", "Meridian Jet"),
    ("SL", "Solstice Air"),
    ("VT", "Vantage Airlines"),
]

# origin, destination, duration (minutes), base price (cents), departure hour
ROUTES = [
    ("JFK", "LHR", 430, 52000, 19),
    ("JFK", "CDG", 450, 56000, 18),
    ("LHR", "CDG", 80, 9500, 8),
    ("LHR", "DXB", 410, 64000, 21),
    ("LHR", "HND", 840, 89000, 12),
    ("LHR", "IST", 230, 18000, 9),
    ("BCN", "LHR", 140, 10000, 7),
    ("CDG", "FCO", 125, 11000, 10),
    ("CDG", "JTR", 200, 23000, 6),
    ("FCO", "JTR", 130, 14000, 15),
    ("DXB", "HND", 580, 78000, 2),
    ("DXB", "JRO", 330, 48000, 4),
    ("IST", "JRO", 470, 61000, 23),
]

# Rough position of each airport (latitude, longitude), used to invent a duration and a price.
POSITIONS = {
    "HND": (35.55, 139.78), "JTR": (36.40, 25.48), "JRO": (-3.43, 37.07),
    "JFK": (40.64, -73.78), "LHR": (51.47, -0.45), "CDG": (49.01, 2.55),
    "DXB": (25.25, 55.36), "FCO": (41.80, 12.25), "IST": (41.26, 28.74),
    "BCN": (41.30, 2.08),
}


def _distance_km(a: str, b: str) -> float:
    (lat1, lon1), (lat2, lon2) = POSITIONS[a], POSITIONS[b]
    p1, p2 = radians(lat1), radians(lat2)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin((radians(lon2) - radians(lon1)) / 2) ** 2
    return 12742 * asin(sqrt(h))


def _all_routes() -> list[tuple[str, str, int, int, int]]:
    """The hand-made routes first (their numbers never change), then every other city pair,
    so a search between any two airports finds a flight."""
    routes = list(ROUTES)
    known = {frozenset((a, b)) for a, b, *_ in routes}
    codes = [row[0] for row in AIRPORTS]
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            if frozenset((a, b)) in known:
                continue
            km = _distance_km(a, b)
            minutes = int(40 + km / 13.5)                 # about 800 km/h plus taxiing
            base = int((3500 + km * 7.5) / 100) * 100     # cents, cheaper per km on long trips
            routes.append((a, b, minutes, base, 6 + (len(routes) * 5) % 16))
    return routes


def seed_demo_data(days: int = 90, start: date | None = None) -> int:
    """Insert whatever is missing: airports, airlines and flights for the next N days.

    Safe to run again: existing rows are kept, so it also tops up flights as time passes.
    Returns the number of flights created.
    """
    start = start or date.today()

    have_airports = set(db.session.scalars(select(Airport.code)))
    for code, city, country, name, slug, blurb, rank in AIRPORTS:
        if code not in have_airports:
            db.session.add(Airport(code=code, city=city, country=country, name=name,
                                   slug=slug, blurb=blurb, featured_rank=rank))

    have_airlines = set(db.session.scalars(select(Airline.code)))
    for code, name in AIRLINES:
        if code not in have_airlines:
            db.session.add(Airline(code=code, name=name))

    first = datetime.combine(start, time.min)
    existing = set(db.session.execute(
        select(Flight.flight_no, Flight.departs_at).where(Flight.departs_at >= first)).all())

    flights = []
    for index, (a, b, minutes, base, hour) in enumerate(_all_routes()):
        for direction, (origin, dest, dep_hour) in enumerate(
            [(a, b, hour), (b, a, (hour + 6) % 24)]
        ):
            flight_no = f"SP{100 + index * 2 + direction}"
            for offset in range(days):
                day = start + timedelta(days=offset)
                departs = datetime.combine(day, time(dep_hour, 0))
                if (flight_no, departs) in existing:
                    continue
                weekend = 1.12 if day.weekday() >= 4 else 1.0   # Fri-Sun cost more
                last_minute = 1 + max(0, 14 - offset) * 0.01      # closer dates cost more
                price = int(base * weekend * last_minute / 100) * 100
                seats = 40 + (index * 37 + direction * 13 + offset * 11) % 110
                flights.append(Flight(
                    flight_no=flight_no, origin_code=origin, destination_code=dest,
                    departs_at=departs, arrives_at=departs + timedelta(minutes=minutes),
                    price_cents=price, seats_available=seats,
                    airline_code=AIRLINES[index % len(AIRLINES)][0],   # one carrier per route, both ways
                ))
    db.session.add_all(flights)
    db.session.commit()
    return len(flights)