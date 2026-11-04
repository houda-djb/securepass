"""Seasons and best months, for "Where to go this season" and "Plan by month".

Seasons follow the northern hemisphere. Southern places just list their real best months, so
the same code works for them.
"""
from datetime import date

SEASONS = {
    "winter": (12, 1, 2),
    "spring": (3, 4, 5),
    "summer": (6, 7, 8),
    "autumn": (9, 10, 11),
}
SEASON_ORDER = ("winter", "spring", "summer", "autumn")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")
STYLES = {"beach": "Beach", "city": "City break", "culture": "Culture",
          "nature": "Nature", "desert": "Desert"}


def season_of(day: date) -> str:
    return next(name for name, months in SEASONS.items() if day.month in months)


def clean_season(raw: str | None, today: date) -> str:
    """The season asked for, or the current one when the value is missing or unknown."""
    return raw if raw in SEASONS else season_of(today)


def clean_month(raw: str | None) -> int | None:
    """A month number from 1 to 12, or None."""
    if raw and raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 12:
        return int(raw)
    return None


def best_time_text(months: list[int]) -> str:
    """[3, 4, 5, 9, 10, 11] becomes "Mar to May, Sep to Nov". December and January join up."""
    if not months:
        return ""
    present = set(months)
    if len(present) == 12:
        return "All year"
    # Start each run at a month whose previous month is missing, so Dec to Feb stays one run.
    starts = [m for m in sorted(present) if (m - 2) % 12 + 1 not in present]
    runs = []
    for start in starts:
        end = start
        while end % 12 + 1 in present:
            end = end % 12 + 1
        runs.append((start, end))
    short = [m[:3] for m in MONTH_NAMES]
    return ", ".join(short[a - 1] if a == b else f"{short[a - 1]} to {short[b - 1]}" for a, b in runs)


def fits(country, months: tuple[int, ...] | list[int]) -> int:
    """How many of the given months are among the country's best months."""
    return len(set(country.months) & set(months))
