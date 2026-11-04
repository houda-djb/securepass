"""The demo payment options. Nothing here ever touches real money or real card data.

The visitor picks one of a fixed list. Only the short key is stored, and anything that is not
on the list is replaced by the default, so a forged form value can never reach the database.
"""
DEFAULT_METHOD = "card"

# key: (label, one line shown at checkout, what happens next)
METHODS = {
    "card": ("Bank card", "Visa or Mastercard. Demo only: no card number is asked for.",
             "Paid by card (demo)."),
    "cib": ("CIB card", "Algerian interbank card. Demo only: no card number is asked for.",
            "Paid with a CIB card (demo)."),
    "baridimob": ("BaridiMob", "Pay from the BaridiMob app. Demo only: nothing is sent to the app.",
                  "Paid with BaridiMob (demo)."),
    "cash": ("Cash at an agency", "Pay in cash at a partner agency before departure. Demo only.",
             "To pay in cash at an agency (demo)."),
}


def clean_method(raw) -> str:
    return raw if isinstance(raw, str) and raw in METHODS else DEFAULT_METHOD


def method_label(key: str) -> str:
    return METHODS.get(key, METHODS[DEFAULT_METHOD])[0]


def method_outcome(key: str) -> str:
    return METHODS.get(key, METHODS[DEFAULT_METHOD])[2]
