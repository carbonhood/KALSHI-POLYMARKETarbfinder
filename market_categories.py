# Market category classification for the arb finder.
import re

from config import ENABLED_CATEGORIES, MAX_HOLD_DAYS_BY_CATEGORY
from market_utils import days_until_resolution, utc_now

# --- Category patterns ---

MACRO_PATTERNS = (
    (re.compile(r"\b(federal reserve|fomc|fed funds|fed rate|interest rate)\b", re.I), "macro"),
    (re.compile(r"\b(bank of korea|bok|bank of japan|boj|ecb|european central bank|bank of england|boe|rba|reserve bank)\b", re.I), "macro"),
    (re.compile(r"\b(cpi|inflation|pce|consumer price)\b", re.I), "macro"),
    (re.compile(r"\b(unemployment|u-3|u3|nonfarm|payroll|jobs added|nfp)\b", re.I), "macro"),
    (re.compile(r"\b(gdp|gross domestic|treasury|yield|retail sales)\b", re.I), "macro"),
)

POLITICS_PATTERNS = (
    (re.compile(r"\b(senate race|house race|gubernatorial|midterm)\b", re.I), "politics_elections"),
    (re.compile(r"\bwill (the )?(republicans|democrats) win the senate race in\b", re.I), "politics_elections"),
    (re.compile(r"\bwill (the )?(republicans|democrats) win the .+ senate race\b", re.I), "politics_elections"),
    (re.compile(r"\bwill (the )?(republicans|democrats) win the .+ senate\b", re.I), "politics_elections"),
    (re.compile(r"\bwill (the )?(republicans|democrats) win the .+ house race\b", re.I), "politics_elections"),
    (re.compile(r"\bwill .+ win the (senate|house) race\b", re.I), "politics_elections"),
    (re.compile(r"\b(control of (the )?(senate|house))\b", re.I), "politics_elections"),
    (re.compile(r"\bwill (the )?(republicans|democrats) control the (senate|house)\b", re.I), "politics_elections"),
    (re.compile(r"\b(presidential run|announce a run for president|primary election)\b", re.I), "politics_elections"),
    (re.compile(r"\bnext (prime minister|president) of\b", re.I), "politics_elections"),
    (re.compile(r"\bSENATE[A-Z]{2}-\d+\b"), "politics_elections"),
    (re.compile(r"\bHOUSE[A-Z]{2}-\d+\b"), "politics_elections"),
)

GEOPOLITICS_PATTERNS = (
    (re.compile(r"\b(meet|meeting|summit|talks).+(putin|zelenskyy|xi|trump|modi)\b", re.I), "geopolitics"),
    (re.compile(r"\b(invade|invasion|ceasefire|recognize|annex)\b", re.I), "geopolitics"),
    (re.compile(r"\b(nato|un security|sanctions on|tariff)\b", re.I), "geopolitics"),
)

SPORTS_PM_PATTERNS = (
    (re.compile(r"\b vs\.?\b", re.I), "sports_pm"),
    (re.compile(r"\bwill .+ win on \d{4}-\d{2}-\d{2}\b", re.I), "sports_pm"),
    (re.compile(r"\b(nfl|nba|mlb|nhl|mls|ufc)\b.*\b(winner|win)\b", re.I), "sports_pm"),
    (re.compile(r"\b(super bowl|world series)\b", re.I), "sports_pm"),
)

CRYPTO_PATTERNS = (
    (re.compile(r"\b(bitcoin|btc|ethereum|eth)\b.*\b(above|below|reach|hit)\b", re.I), "crypto"),
    (re.compile(r"\bwill (bitcoin|btc|ethereum|eth)\b", re.I), "crypto"),
)

LEGAL_PATTERNS = (
    (re.compile(r"\b(convicted|indicted|charged|acquitted|sentenced|found guilty)\b", re.I), "legal"),
)

MACRO_EVENT_TYPES = {"central_bank", "econ_threshold", "econ_release", "threshold"}
POLITICS_EVENT_TYPES = {"election"}
SPORTS_PM_EVENT_TYPES = {"sports_pm"}
CRYPTO_EVENT_TYPES = {"crypto_threshold"}
LEGAL_EVENT_TYPES = {"legal_outcome"}
LEGACY_SPORTS_EVENT_TYPES = {"sports_match", "esports_match", "golf_tournament"}

# Corporate earnings / bank-specific metrics are not cross-venue macro events.
CORPORATE_EARNINGS_PATTERN = re.compile(
    r"\b(q[1-4]|provision for credit|earnings per share|eps|revenue be|net income)\b",
    re.I,
)


def _combined_text(market):
    return " ".join([
        market.get("market_question", ""),
        market.get("event_title", ""),
        market.get("event_ticker", "") or market.get("ticker", ""),
        " ".join(market.get("tags") or []),
    ])


def classify_market_category(market):
    """Return primary category string or None."""
    event_key = market.get("event_key")
    if event_key:
        event_type = event_key[0]
        if event_type in MACRO_EVENT_TYPES:
            return "macro"
        if event_type in POLITICS_EVENT_TYPES:
            return "politics_elections"
        if event_type in SPORTS_PM_EVENT_TYPES and "sports_pm" in ENABLED_CATEGORIES:
            return "sports_pm"
        if event_type in CRYPTO_EVENT_TYPES and "crypto" in ENABLED_CATEGORIES:
            return "crypto"
        if event_type in LEGAL_EVENT_TYPES and "legal" in ENABLED_CATEGORIES:
            return "legal"
        if event_type in LEGACY_SPORTS_EVENT_TYPES:
            return None

    text = _combined_text(market)

    if CORPORATE_EARNINGS_PATTERN.search(text):
        return None

    category_checks = []
    if "sports_pm" in ENABLED_CATEGORIES:
        category_checks.append((SPORTS_PM_PATTERNS, "sports_pm"))
    if "legal" in ENABLED_CATEGORIES:
        category_checks.append((LEGAL_PATTERNS, "legal"))
    if "crypto" in ENABLED_CATEGORIES:
        category_checks.append((CRYPTO_PATTERNS, "crypto"))
    category_checks.extend([
        (POLITICS_PATTERNS, "politics_elections"),
        (GEOPOLITICS_PATTERNS, "geopolitics"),
        (MACRO_PATTERNS, "macro"),
    ])

    for patterns, category in category_checks:
        for pattern, cat in patterns:
            if pattern.search(text):
                return cat

    tags = [t.lower() for t in (market.get("tags") or [])]
    if any(t in ("finance", "economics", "fed-rates", "fed") for t in tags):
        return "macro"
    if any(t in ("politics", "us-politics", "elections") for t in tags):
        return "politics_elections"
    if any(t in ("geopolitics", "world", "foreign-policy") for t in tags):
        return "geopolitics"
    if "sports_pm" in ENABLED_CATEGORIES and any(t in ("sports", "nfl", "nba", "mlb") for t in tags):
        return "sports_pm"
    if "crypto" in ENABLED_CATEGORIES and any(t in ("crypto", "bitcoin", "ethereum") for t in tags):
        return "crypto"

    return None


def market_hold_days(market):
    event_key = market.get("event_key")
    if event_key and event_key[0] == "election" and len(event_key) >= 4:
        year = event_key[-1]
        if isinstance(year, int) and year > 2000:
            from datetime import datetime, timezone
            election = datetime(year, 11, 5, tzinfo=timezone.utc)
            return max((election - utc_now()).total_seconds() / 86400, 0.25)

    for field in ("days_to_resolution", "end_date", "close_time"):
        if field == "days_to_resolution" and market.get(field) is not None:
            return max(float(market["days_to_resolution"]), 0.25)
        days = days_until_resolution(market.get(field))
        if days is not None and days >= 0:
            return max(days, 0.25)
    return 365.0


def is_enabled_category(market):
    """True if market matches an enabled category and passes hold limit."""
    category = classify_market_category(market)
    if not category or category not in ENABLED_CATEGORIES:
        return False

    max_hold = MAX_HOLD_DAYS_BY_CATEGORY.get(category, 45)
    if market_hold_days(market) > max_hold:
        return False

    market["category"] = category
    market["hold_days_estimate"] = round(market_hold_days(market), 2)
    return True


def filter_by_enabled_categories(markets):
    """Keep markets in enabled categories within per-category hold limits."""
    return [m for m in markets if is_enabled_category(m)]


def is_macro_market(market):
    return classify_market_category(market) == "macro"


def filter_macro_markets(markets):
    return filter_by_enabled_categories([m for m in markets if classify_market_category(m) == "macro"])
