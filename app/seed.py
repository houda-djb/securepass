"""Demo data: airports and a daily flight on every route for the next N days.

Everything is deterministic (no randomness) so the demo behaves the same every time.
"""
from datetime import date, datetime, time, timedelta

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


def seed_demo_data(days: int = 90, start: date | None = None) -> int:
    """Insert airports and flights. Returns the number of flights created."""
    start = start or date.today()

    for code, city, country, name, slug, blurb, rank in AIRPORTS:
        db.session.add(Airport(code=code, city=city, country=country, name=name,
                               slug=slug, blurb=blurb, featured_rank=rank))

    for code, name in AIRLINES:
        db.session.add(Airline(code=code, name=name))

    flights = []
    for index, (a, b, minutes, base, hour) in enumerate(ROUTES):
        for direction, (origin, dest, dep_hour) in enumerate(
            [(a, b, hour), (b, a, (hour + 6) % 24)]
        ):
            flight_no = f"SP{100 + index * 2 + direction}"
            for offset in range(days):
                day = start + timedelta(days=offset)
                departs = datetime.combine(day, time(dep_hour, 0))
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