"""Business rules for one raw event. Amounts are integer minor units; FX rates are fixed per day."""
RATES = {"USD": (1, 1), "EUR": (108, 100), "GBP": (127, 100), "JPY": (67, 10000)}  # to USD cents: n/d


def transform(e):
    """Returns (event_id, user, usd_cents) for a settled event, else None."""
    if e.get("status") != "settled":
        return None
    n, d = RATES[e["currency"]]
    return e["id"], e["user"].strip().lower(), e["amount"] * n // d
