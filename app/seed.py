"""Demo data: airports, countries and a daily flight on every route for the next N days.

Everything is deterministic (no randomness) so the demo behaves the same every time.
"""
from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select

from app.extensions import db
from app.models import Airline, Airport, Country, Flight

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
    # Added in Phase 19. The first ten above keep their order, so flight numbers never change.
    ("ALG", "Alger", "Algeria", "Houari Boumediene", "alger",
     "The white city on the bay: the Casbah, the seafront and the Martyrs' Memorial.", None),
    ("ORN", "Oran", "Algeria", "Ahmed Ben Bella", "oran",
     "Algeria's second city, with a lively corniche, raï music and Santa Cruz fort above the bay.", None),
    ("CZL", "Constantine", "Algeria", "Mohamed Boudiaf", "constantine",
     "The city of bridges, built on a rock above a deep gorge.", None),
    ("AAE", "Annaba", "Algeria", "Rabah Bitat", "annaba",
     "A relaxed port city with beaches, Roman ruins at Hippo and a mild climate.", None),
    ("TLM", "Tlemcen", "Algeria", "Messali El Hadj", "tlemcen",
     "Andalusian architecture, mosques and gardens in the old capital of the west.", None),
    ("BJA", "Béjaïa", "Algeria", "Soummam Abane Ramdane", "bejaia",
     "Cliffs, coves and mountain roads where Kabylia meets the sea.", None),
    ("GHA", "Ghardaïa", "Algeria", "Noumérat", "ghardaia",
     "The M'zab valley: five fortified towns of white and ochre houses in the Sahara.", None),
    ("TMR", "Tamanrasset", "Algeria", "Aguenar Hadj Bey Akhamok", "tamanrasset",
     "The gateway to the Hoggar mountains and some of the clearest night skies on earth.", None),
    ("TUN", "Tunis", "Tunisia", "Tunis-Carthage", "tunis",
     "A medina of blue doors and souks, with the ruins of Carthage a short ride away.", None),
    ("CMN", "Casablanca", "Morocco", "Mohammed V", "casablanca",
     "Morocco's big modern city, home of the Hassan II Mosque on the Atlantic shore.", None),
    ("CAI", "Cairo", "Egypt", "Cairo International", "cairo",
     "The pyramids, the Nile and one of the world's great old bazaars.", None),
    ("JED", "Jeddah", "Saudi Arabia", "King Abdulaziz", "jeddah",
     "A Red Sea port with a UNESCO-listed old town and a long waterfront.", None),
    ("DOH", "Doha", "Qatar", "Hamad International", "doha",
     "A skyline on the Gulf, the Museum of Islamic Art and the Souq Waqif.", None),
    ("MAD", "Madrid", "Spain", "Adolfo Suárez Madrid-Barajas", "madrid",
     "Grand boulevards, world-class museums and late dinners.", None),
    ("MRS", "Marseille", "France", "Provence", "marseille",
     "France's oldest port, with a Vieux-Port full of boats and the calanques just outside.", None),
    ("YUL", "Montréal", "Canada", "Pierre Elliott Trudeau", "montreal",
     "A bilingual city of festivals, old stone streets and a large Algerian community.", None),
    ("KUL", "Kuala Lumpur", "Malaysia", "Kuala Lumpur International", "kuala-lumpur",
     "The Petronas Towers, street food at every corner and rainforest within reach.", None),
    ("DPS", "Bali", "Indonesia", "Ngurah Rai", "bali",
     "Rice terraces, temples and surf beaches on the island of the gods.", None),
]

# Cities where the first ten airports' original blurbs were empty; filled in for old databases too.
EXTRA_BLURBS = {
    "JFK": "The skyline, Central Park and a different neighbourhood for every mood.",
    "LHR": "Royal parks, museums that are free to enter and a pub on every corner.",
    "CDG": "Cafés, the Seine and some of the best food walks in Europe.",
    "DXB": "A city of record-breaking towers, desert safaris and Gulf beaches.",
    "FCO": "Two thousand years of history in a city you can cross on foot.",
    "IST": "Two continents, a skyline of domes and minarets, and the Grand Bazaar.",
    "BCN": "Gaudí, beaches and tapas, all within a short metro ride.",
}

# slug, name, blurb, why go and when, best months, trip styles
COUNTRIES = [
    ("algeria", "Algeria", "The largest country in Africa, with a Mediterranean coast, Roman ruins, the Kabylia mountains and the Sahara.",
     "Mild on the coast in spring and autumn, and the Sahara is at its best from October to March.", "3,4,5,9,10,11", "beach,culture,desert,nature"),
    ("tunisia", "Tunisia", "Beaches, medinas and the ruins of Carthage, close to Algeria and easy to reach.",
     "Warm sea from June, and quieter, cheaper beaches in May and September.", "5,6,9,10", "beach,culture,desert"),
    ("morocco", "Morocco", "Imperial cities, the Atlantic coast and the Atlas mountains.",
     "Pleasant in spring and autumn, before and after the summer heat inland.", "3,4,5,10,11", "city,culture,desert"),
    ("egypt", "Egypt", "The pyramids, the Nile and Red Sea reefs.",
     "Cool and dry from October to April, the best time for the Nile and the pyramids.", "10,11,12,1,2,3,4", "culture,beach"),
    ("saudi-arabia", "Saudi Arabia", "Old trading ports on the Red Sea and the holy cities.",
     "Mild winter weather from November to March.", "11,12,1,2,3", "city,culture"),
    ("qatar", "Qatar", "A modern capital on the Gulf with museums, souks and desert dunes.",
     "Cool and dry from November to March.", "11,12,1,2,3", "city,desert"),
    ("united-arab-emirates", "United Arab Emirates", "Skyscrapers, malls, desert safaris and warm Gulf beaches.",
     "Beach weather without the extreme summer heat, from November to March.", "11,12,1,2,3", "city,beach,desert"),
    ("turkey", "Turkey", "Istanbul's two continents, Cappadocia's valleys and a long Aegean coast.",
     "Warm, not too hot, in spring and early autumn.", "4,5,6,9,10", "city,culture,beach"),
    ("greece", "Greece", "White villages, ancient sites and clear water on hundreds of islands.",
     "The sea is warm enough to swim from June to September.", "5,6,7,8,9", "beach,culture"),
    ("italy", "Italy", "Rome, Florence, Venice and the best food in Europe.",
     "Comfortable weather and smaller crowds in spring and autumn.", "4,5,6,9,10", "city,culture"),
    ("france", "France", "Paris, Provence and the Riviera.",
     "Paris at its best in spring and early autumn, with Christmas markets in December.", "4,5,6,9,12", "city,culture"),
    ("spain", "Spain", "Barcelona's beaches, Madrid's museums and Andalusian old towns.",
     "Warm sea in Barcelona from June, mild city weather in spring and autumn.", "4,5,6,9,10", "city,beach,culture"),
    ("united-kingdom", "United Kingdom", "London's museums, royal parks and day trips to historic towns.",
     "The longest days and mildest weather, from May to September.", "5,6,7,8,9", "city,culture"),
    ("united-states", "United States", "New York's skyline, and a whole continent beyond it.",
     "New York is best in spring and autumn, and festive in December.", "4,5,9,10,12", "city"),
    ("canada", "Canada", "Montréal's festivals and old streets, with lakes and forests close by.",
     "Festivals in summer, and red autumn leaves in September and October.", "6,7,8,9,10", "city,nature"),
    ("japan", "Japan", "Tokyo's neon and quiet shrines, bullet trains and mountain towns.",
     "Cherry blossom in March and April, and autumn leaves in November.", "3,4,10,11", "city,culture,nature"),
    ("malaysia", "Malaysia", "Kuala Lumpur's towers and street food, with rainforest and islands nearby.",
     "Drier weather in Kuala Lumpur from May to August.", "5,6,7,8", "city,nature"),
    ("indonesia", "Indonesia", "Bali's rice terraces, temples and surf beaches.",
     "Bali's dry season runs from May to September.", "5,6,7,8,9", "beach,nature,culture"),
    ("tanzania", "Tanzania", "The Serengeti, Kilimanjaro and the spice island of Zanzibar.",
     "The dry season, from June to October, is the best time for game drives.", "6,7,8,9,10", "nature,beach"),
]

# The cities that make up Algeria's domestic network. Alger is the hub for everything else.
HUB = "ALG"
DOMESTIC = ["ORN", "CZL", "AAE", "TLM", "BJA", "GHA", "TMR"]

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
    "ALG": (36.69, 3.22), "ORN": (35.62, -0.62), "CZL": (36.28, 6.62), "AAE": (36.82, 7.81),
    "TLM": (35.02, -1.45), "BJA": (36.71, 5.07), "GHA": (32.38, 3.79), "TMR": (22.81, 5.45),
    "TUN": (36.85, 10.23), "CMN": (33.37, -7.59), "CAI": (30.12, 31.41), "JED": (21.68, 39.16),
    "DOH": (25.27, 51.61), "MAD": (40.49, -3.57), "MRS": (43.44, 5.22), "YUL": (45.47, -73.74),
    "KUL": (2.75, 101.71), "DPS": (-8.75, 115.17),
}


def _distance_km(a: str, b: str) -> float:
    (lat1, lon1), (lat2, lon2) = POSITIONS[a], POSITIONS[b]
    p1, p2 = radians(lat1), radians(lat2)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin((radians(lon2) - radians(lon1)) / 2) ** 2
    return 12742 * asin(sqrt(h))


def _route(a: str, b: str, number: int) -> tuple[str, str, int, int, int]:
    km = _distance_km(a, b)
    minutes = int(40 + km / 13.5)                 # about 800 km/h plus taxiing
    base = int((3500 + km * 7.5) / 100) * 100     # cents, cheaper per km on long trips
    return (a, b, minutes, base, 6 + (number * 5) % 16)


def _all_routes() -> list[tuple[str, str, int, int, int]]:
    """Every route, in a fixed order, because a route's position decides its flight number.

    1. The hand-made routes, then every other pair of the first ten airports (Phase 15).
    2. Alger to every other airport, then the domestic Algerian network (Phase 19).
    New routes are only ever added at the end, so existing flight numbers never change.
    """
    routes = list(ROUTES)
    known = {frozenset((a, b)) for a, b, *_ in routes}
    original = [row[0] for row in AIRPORTS[:10]]
    for i, a in enumerate(original):
        for b in original[i + 1:]:
            if frozenset((a, b)) not in known:
                known.add(frozenset((a, b)))
                routes.append(_route(a, b, len(routes)))

    spokes = [row[0] for row in AIRPORTS if row[0] != HUB]
    for code in spokes:
        if frozenset((HUB, code)) not in known:
            known.add(frozenset((HUB, code)))
            routes.append(_route(HUB, code, len(routes)))
    for i, a in enumerate(DOMESTIC):
        for b in DOMESTIC[i + 1:]:
            if frozenset((a, b)) not in known:
                known.add(frozenset((a, b)))
                routes.append(_route(a, b, len(routes)))
    return routes


def seed_demo_data(days: int = 90, start: date | None = None) -> int:
    """Insert whatever is missing: airports, airlines and flights for the next N days.

    Safe to run again: existing rows are kept, so it also tops up flights as time passes.
    Returns the number of flights created.
    """
    start = start or date.today()

    have_airports = {a.code: a for a in db.session.scalars(select(Airport))}
    for code, city, country, name, slug, blurb, rank in AIRPORTS:
        if code not in have_airports:
            db.session.add(Airport(code=code, city=city, country=country, name=name,
                                   slug=slug, blurb=blurb or EXTRA_BLURBS.get(code, ""), featured_rank=rank))
        elif not have_airports[code].blurb and (blurb or EXTRA_BLURBS.get(code)):
            have_airports[code].blurb = blurb or EXTRA_BLURBS[code]   # old databases had empty blurbs
    for code, text in EXTRA_BLURBS.items():
        if code in have_airports and not have_airports[code].blurb:
            have_airports[code].blurb = text

    have_countries = set(db.session.scalars(select(Country.slug)))
    for slug, name, blurb, why, months, styles in COUNTRIES:
        if slug not in have_countries:
            db.session.add(Country(slug=slug, name=name, blurb=blurb, why=why,
                                   best_months=months, styles=styles))

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