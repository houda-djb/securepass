"""Showing prices in Algerian dinars, euros or US dollars.

Prices are stored once, in US dollar cents (whole numbers, never floats). Other currencies are
only a way of showing them, at fixed demo rates that the page says are indicative. Nothing is
ever converted back, so a booking's stored total never changes when the rate does.
"""
from flask import current_app, session

# 1 US dollar = RATE of each currency (demo rates, not live ones).
RATES = {"USD": 1.0, "EUR": 0.92, "DZD": 135.0}
CURRENCIES = tuple(RATES)
FALLBACK = "DZD"


def current_currency() -> str:
    """The visitor's choice, else the site default."""
    choice = session.get("currency")
    if choice in RATES:
        return choice
    default = current_app.config.get("DEFAULT_CURRENCY", FALLBACK)
    return default if default in RATES else FALLBACK


def _group(number: int) -> str:
    return f"{number:,}".replace(",", " ")     # narrow no-break space, as dinars are written


def money(cents: int, decimals: int = 0, currency: str | None = None) -> str:
    """Format US dollar cents in a currency. `decimals` only applies to dollars and euros."""
    currency = currency or current_currency()
    amount = cents / 100 * RATES[currency]
    if currency == "DZD":
        return f"{_group(round(amount))} DZD"
    if currency == "EUR":
        return f"€{amount:,.{decimals}f}"
    return f"${amount:,.{decimals}f}"


def slider_format(currency: str | None = None) -> dict:
    """What the price slider needs to write the same format in the browser."""
    currency = currency or current_currency()
    return {"rate": RATES[currency],
            "pre": {"USD": "$", "EUR": "€", "DZD": ""}[currency],
            "post": " DZD" if currency == "DZD" else ""}
