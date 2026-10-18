"""Server-side validation of the flight search (SR3).

The browser also checks these fields, but that is only a convenience: anyone can
send any URL, so the server never trusts the input.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

IATA_PATTERN = re.compile(r"^[A-Za-z]{3}$")
MAX_PASSENGERS = 9
MAX_DAYS_AHEAD = 365


@dataclass(frozen=True)
class SearchQuery:
    origin: str
    destination: str
    departure: date
    return_date: date | None
    passengers: int


def _parse_date(raw: str) -> date | None:
    if len(raw) != 10:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def validate_search(args, today: date | None = None) -> tuple[SearchQuery | None, dict[str, str]]:
    """Return (query, errors). The query is None whenever there is at least one error."""
    today = today or date.today()
    errors: dict[str, str] = {}

    origin = args.get("origin", "").strip()
    destination = args.get("destination", "").strip()
    departure_raw = args.get("departure", "").strip()
    return_raw = args.get("return", "").strip()
    passengers_raw = args.get("passengers", "").strip()

    if not IATA_PATTERN.match(origin):
        errors["origin"] = "Enter a 3-letter airport code, for example LHR."
    if not IATA_PATTERN.match(destination):
        errors["destination"] = "Enter a 3-letter airport code, for example JFK."
    if not errors and origin.upper() == destination.upper():
        errors["destination"] = "Origin and destination must be different."

    departure = _parse_date(departure_raw)
    if departure is None:
        errors["departure"] = "Choose a valid departure date."
    elif departure < today:
        errors["departure"] = "The departure date can't be in the past."
    elif departure > today + timedelta(days=MAX_DAYS_AHEAD):
        errors["departure"] = "Flights can be searched up to one year ahead."

    return_date = None
    if return_raw:
        return_date = _parse_date(return_raw)
        if return_date is None:
            errors["return"] = "Choose a valid return date."
        elif departure is not None and return_date < departure:
            errors["return"] = "The return date can't be before the departure date."

    passengers = 0
    if passengers_raw.isascii() and passengers_raw.isdigit():
        passengers = int(passengers_raw)
    if not 1 <= passengers <= MAX_PASSENGERS:
        errors["passengers"] = f"Choose between 1 and {MAX_PASSENGERS} passengers."

    if errors:
        return None, errors
    return SearchQuery(origin.upper(), destination.upper(), departure, return_date, passengers), {}