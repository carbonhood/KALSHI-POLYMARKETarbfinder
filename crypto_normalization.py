# Canonical event keys for crypto price threshold markets.
import re

from entity_matching import extract_threshold, normalize_entity

BTC_THRESHOLD = re.compile(
    r"\b(?:bitcoin|btc)\b.*?(?:above|over|below|under|reach|hit)\s+"
    r"(?:\$)?(?P<value>[\d,]+(?:\.\d+)?)\s*k?",
    re.I,
)
ETH_THRESHOLD = re.compile(
    r"\b(?:ethereum|eth)\b.*?(?:above|over|below|under|reach|hit)\s+"
    r"(?:\$)?(?P<value>[\d,]+(?:\.\d+)?)\s*k?",
    re.I,
)
CRYPTO_EXACT_POLY = re.compile(
    r"will (?:bitcoin|btc|ethereum|eth).{0,40}?(?:be|reach|hit)\s+"
    r"(?:\$)?(?P<value>[\d,]+(?:\.\d+)?)\s*k?",
    re.I,
)


def _parse_crypto_value(text, unit_hint=""):
    if not text:
        return None
    cleaned = str(text).replace(",", "").replace("$", "").strip().lower()
    multiplier = 1.0
    if cleaned.endswith("k") or "k" in unit_hint.lower():
        cleaned = cleaned.rstrip("k")
        multiplier = 1000.0
    try:
        value = float(cleaned) * multiplier
    except ValueError:
        return None
    if value >= 10000 and value == int(value):
        return int(value)
    return value


def _detect_asset(text):
    lowered = (text or "").lower()
    if "bitcoin" in lowered or re.search(r"\bbtc\b", lowered):
        return "btc"
    if "ethereum" in lowered or re.search(r"\beth\b", lowered):
        return "eth"
    return None


def extract_crypto_event_key(title, market=None):
    """Return ('crypto_threshold', asset, direction, value) or None."""
    market = market or {}
    combined = f"{market.get('event_title', '')} {title or ''} {market.get('yes_sub_title', '')}"
    asset = _detect_asset(combined)
    if not asset:
        return None

    direction = "above"
    if re.search(r"\b(below|under)\b", combined, re.I):
        direction = "below"

    for pattern in (BTC_THRESHOLD, ETH_THRESHOLD, CRYPTO_EXACT_POLY):
        match = pattern.search(combined)
        if match:
            value = _parse_crypto_value(match.group("value"))
            if value is not None:
                return ("crypto_threshold", asset, direction, value)

    threshold = extract_threshold(title)
    if threshold is not None and asset:
        return ("crypto_threshold", asset, direction, threshold)

    group = market.get("group_item_title") or ""
    if group and asset:
        value = _parse_crypto_value(group)
        if value is not None:
            return ("crypto_threshold", asset, "exact", value)

    return None


def normalize_crypto_outcome(title, market=None):
    event_key = (market or {}).get("event_key") or extract_crypto_event_key(title, market=market)
    if not event_key or event_key[0] != "crypto_threshold":
        return None
    direction = event_key[2]
    value = event_key[3]
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{direction}_{value}"
