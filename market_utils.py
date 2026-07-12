# Helpers for parsing resolution dates and filtering by time horizon.
from datetime import datetime, timedelta, timezone

from config import MAX_DAYS_TO_RESOLUTION


def utc_now():
    return datetime.now(timezone.utc)


def utc_timestamp():
    return int(utc_now().timestamp())


def horizon_end_timestamp(max_days=MAX_DAYS_TO_RESOLUTION):
    return int((utc_now() + timedelta(days=max_days)).timestamp())


def parse_iso_datetime(value):
    """Parse ISO-8601 strings from Polymarket/Kalshi into UTC datetimes."""
    if not value:
        return None

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def days_until_resolution(value):
    """Return days until resolution; negative means already past."""
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return None
    return (parsed - utc_now()).total_seconds() / 86400


def within_resolution_horizon(value, max_days=MAX_DAYS_TO_RESOLUTION):
    days = days_until_resolution(value)
    if days is None:
        return False
    return 0 <= days <= max_days


def is_tradable_binary_book(yes_price, no_price):
    """
    Reject clearly broken or empty books.

    Real YES/NO ask prices should sum to roughly $1. Illiquid tails often
    show nonsense like 0.01 + 0.04 on unrelated legs.
    """
    if yes_price is None or no_price is None:
        return False
    if yes_price <= 0 or no_price <= 0:
        return False

    total = yes_price + no_price
    return 0.88 <= total <= 1.12


def polymarket_horizon_dates(max_days=MAX_DAYS_TO_RESOLUTION):
    """Date strings for Polymarket end_date_min / end_date_max query params."""
    now = utc_now()
    return (
        now.strftime("%Y-%m-%d"),
        (now + timedelta(days=max_days)).strftime("%Y-%m-%d"),
    )
