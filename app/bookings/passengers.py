"""Passenger names on the checkout form (SR3: the server checks every value).

The form sends first_name_1, last_name_1, first_name_2, ... one pair per passenger.
Only names are collected. No passport, date of birth or payment data is stored.
"""
import re

NAME_MAX = 40
# Letters from any language, joined by single spaces, hyphens or apostrophes
# (Anne-Marie, O'Brien, de la Cruz). No digits, symbols, markup or control characters.
NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '’-][^\W\d_]+)*$")


def field_names(position: int) -> tuple[str, str]:
    return f"first_name_{position}", f"last_name_{position}"


def submitted_values(form, count: int) -> dict[str, str]:
    """The raw (trimmed, shortened) values to show back in the form."""
    values = {}
    for position in range(1, count + 1):
        for name in field_names(position):
            values[name] = " ".join(form.get(name, "").split())[:NAME_MAX + 10]
    return values


def read_passengers(form, count: int):
    """Return (names, errors). `names` is a list of (first, last) pairs.

    If the form carries no name fields at all, there is nothing to check and no names are
    saved (older links and API-style posts keep working). If it carries any, every passenger
    needs both names.
    """
    values = submitted_values(form, count)
    if not any(name in form for position in range(1, count + 1) for name in field_names(position)):
        return [], {}

    errors: dict[str, str] = {}
    names = []
    for position in range(1, count + 1):
        pair = []
        for name, label in zip(field_names(position), ("first name", "last name")):
            value = values[name]
            if not value:
                errors[name] = f"Enter the {label}."
            elif len(value) > NAME_MAX:
                errors[name] = f"Use at most {NAME_MAX} characters."
            elif not NAME_PATTERN.match(value):
                errors[name] = "Use letters only (spaces, hyphens and apostrophes are fine)."
            pair.append(value)
        names.append(tuple(pair))
    return ([] if errors else names), errors
