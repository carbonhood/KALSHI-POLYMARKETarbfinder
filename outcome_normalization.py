# Map market titles to canonical event keys and outcomes for cross-platform matching.
import re
from datetime import datetime

from crypto_normalization import extract_crypto_event_key, normalize_crypto_outcome
from entity_matching import extract_matchup, extract_threshold, normalize_entity
from legal_normalization import extract_legal_event_key, normalize_legal_outcome
from politics_normalization import extract_politics_event_key, normalize_politics_outcome
from sports_pm_normalization import extract_sports_pm_event_key, normalize_sports_pm_outcome

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

CENTRAL_BANKS = {
    "bank of korea": "bank_of_korea",
    "bok": "bank_of_korea",
    "federal reserve": "federal_reserve",
    "fed": "federal_reserve",
    "fomc": "federal_reserve",
    "european central bank": "ecb",
    "ecb": "ecb",
    "bank of england": "bank_of_england",
    "boe": "bank_of_england",
}

MONTH_IN_TITLE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.IGNORECASE,
)
YEAR_IN_TITLE = re.compile(r"\b(20\d{2})\b")

KALSHI_RATE_OUTCOME = re.compile(
    r"\b(maintain current rate|hike 1-25bps|hike more than 25bps|cut 1-25bps|cut more than 25bps)\b",
    re.IGNORECASE,
)

POLY_RATE_OUTCOME = re.compile(
    r"\b(no change|increase|decrease)\b",
    re.IGNORECASE,
)

THRESHOLD_IN_TITLE = re.compile(
    r"\b(?:above|over|below|under|at least|more than|less than)\s+"
    r"(?:\$)?(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|k|m|million|billion|jobs|bps|basis points)?",
    re.IGNORECASE,
)

JOBS_ADDED = re.compile(
    r"(?:above|over|at least|more than)\s+(?P<amount>\d[\d,]*)\s+jobs?\s+be\s+added",
    re.IGNORECASE,
)

UNEMPLOYMENT_ABOVE = re.compile(
    r"unemployment rate.*?(?:above|over)\s+(?P<pct>\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

CPI_PATTERN = re.compile(
    r"\b(?:cpi|inflation).*?(?:above|over|below|under)\s+(?P<pct>\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

EXACTLY_BUCKET = re.compile(
    r"exactly\s+(?P<value>-?\d+(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)

POLY_EXACT_BUCKET = re.compile(
    r"will\s+(?:core\s+)?cpi\s+(?:mom|yoy)?\s+be\s+(?P<value>-?\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

POLY_AT_LEAST_BUCKET = re.compile(
    r"will\s+(?:core\s+)?cpi\s+(?:mom|yoy)?\s+be\s+(?P<value>\d+(?:\.\d+)?)\s*%\s+or\s+more",
    re.IGNORECASE,
)

POLY_AT_MOST_BUCKET = re.compile(
    r"will\s+(?:core\s+)?cpi\s+(?:mom|yoy)?\s+be\s+(?P<value>-?\d+(?:\.\d+)?)\s*%\s+or\s+less",
    re.IGNORECASE,
)

KALSHI_RISE_MORE_THAN = re.compile(
    r"rise\s+more\s+than\s+(?P<value>-?\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

KALSHI_EVENT_TICKER_DATE = re.compile(
    r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b",
    re.IGNORECASE,
)

ECON_INDICATOR_PATTERNS = (
    (re.compile(r"core\s+cpi\s+(?:mom|month[- ]over[- ]month)|cpi\s+core\s+month[- ]over[- ]month", re.I), "cpi_core_mom"),
    (re.compile(r"core\s+cpi\s+(?:yoy|year[- ]over[- ]year)|cpi\s+core\s+year[- ]over[- ]year", re.I), "cpi_core_yoy"),
    (re.compile(r"cpi\s+year[- ]over[- ]year|cpi\s+yoy\b", re.I), "cpi_yoy"),
    (re.compile(r"cpi\s+month[- ]over[- ]month|cpi\s+mom\b", re.I), "cpi_mom"),
    (re.compile(r"\b(?:nonfarm|payroll|nfp)\b.*\b(?:payroll|jobs)\b|\bjobs?\s+be\s+added\b", re.I), "nfp_jobs"),
    (re.compile(r"\b(?:u-?3|unemployment)\b.*\bunemployment\b|\bunemployment\s+rate\b", re.I), "u3_unemployment"),
    (re.compile(r"\bgdp\b", re.I), "gdp"),
)

KALSHI_RULES_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2}),\s+(20\d{2})\b",
    re.IGNORECASE,
)

ESPORTS_MATCH_IN_TITLE = re.compile(
    r"(?:in the\s+)?(.+?)\s+vs\.?\s+(.+?)(?:\s+call|\s+match|\s+bo\d|\?|$)",
    re.IGNORECASE,
)

GOLF_WINNER = re.compile(
    r"will\s+(.+?)\s+win\s+(?:the\s+)?(?:the\s+)?(.+?)\?",
    re.IGNORECASE,
)


def _month_token(text):
    match = MONTH_IN_TITLE.search(text or "")
    if not match:
        return None
    return MONTHS.get(match.group(1).lower())


def _year_token(text):
    match = YEAR_IN_TITLE.search(text or "")
    if match:
        return int(match.group(1))
    return None


def _detect_central_bank(text):
    lowered = (text or "").lower()
    for phrase, bank_id in CENTRAL_BANKS.items():
        if phrase in lowered:
            return bank_id
    return None


def _game_date_from_market(market):
    for field in ("occurrence_datetime", "close_time", "end_date"):
        value = market.get(field)
        if not value:
            continue
        try:
            if "T" in str(value):
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
            return str(value)[:10]
        except ValueError:
            continue

    rules = market.get("rules_primary") or ""
    match = KALSHI_RULES_DATE.search(rules)
    if match:
        month = MONTHS.get(match.group(1).lower())
        if month:
            return f"{match.group(3)}-{month:02d}-{int(match.group(2)):02d}"

    return None


def _year_from_date(value):
    if not value:
        return None
    text = str(value)
    match = re.search(r"(20\d{2})", text)
    if match:
        return int(match.group(1))
    return None


def extract_central_bank_event_key(title, event_title=None, market=None):
    """Return ('central_bank', bank_id, year, month) or None."""
    combined = f"{event_title or ''} {title or ''}"
    bank_id = _detect_central_bank(combined)
    if not bank_id:
        return None

    month = _month_token(combined)
    year = _year_token(combined) or _year_from_date((market or {}).get("end_date"))
    year = year or _year_from_date((market or {}).get("close_time"))
    if not month or not year:
        return None

    return ("central_bank", bank_id, year, month)


def _canonical_golf_tournament(name):
    lowered = (name or "").lower()
    if "open championship" in lowered or "the open" in lowered or "british open" in lowered:
        return "the_open"
    if "wimbledon" in lowered:
        return "wimbledon"
    return normalize_entity(name).replace(" ", "_")


def extract_esports_match_event_key(title, market=None):
    """
    Parse head-to-head esports matchups embedded in Kalshi prop titles.

    Example: "... in the Toronto KOI vs. Paris Gentle Mates Call of Duty ..."
    """
    match = ESPORTS_MATCH_IN_TITLE.search(title or "")
    if not match:
        return None

    team_a = normalize_entity(match.group(1))
    team_b = normalize_entity(match.group(2))
    if len(team_a) < 3 or len(team_b) < 3:
        return None

    game_date = _game_date_from_market(market or {})
    if not game_date:
        return None

    return ("esports_match", tuple(sorted((team_a, team_b))), game_date)


def extract_golf_event_key(title, market=None):
    """Return ('golf_tournament', tournament_id, year) for golfer winner markets."""
    lowered = (title or "").lower()
    if "open championship" not in lowered and "wimbledon" not in lowered:
        return None
    if any(marker in lowered for marker in ("top 5", "top 10", "top 20", "make the cut")):
        return None

    year = _year_token(title) or _year_from_date((market or {}).get("close_time"))
    if not year:
        return None

    if "open championship" in lowered or "the open" in lowered:
        return ("golf_tournament", "the_open", year)
    if "wimbledon" in lowered:
        return ("golf_tournament", "wimbledon", year)

    return None


def extract_sports_event_key(title, market=None):
    """Return ('sports_match', team_a, team_b, date) or None."""
    matchup = extract_matchup(title)
    if not matchup and market:
        matchup = market.get("event_matchup")

    if not matchup:
        return None

    game_date = _game_date_from_market(market or {})
    if not game_date:
        return None

    return ("sports_match", matchup[0], matchup[1], game_date)


def _parse_percent_value(text):
    if text is None:
        return None
    cleaned = str(text).strip().replace(",", "").replace("≤", "").replace("≥", "").replace("%", "")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value.is_integer():
        return int(value)
    return value


def _month_year_from_event_ticker(market):
    ticker = (market or {}).get("event_ticker") or (market or {}).get("ticker") or ""
    match = KALSHI_EVENT_TICKER_DATE.search(ticker)
    if not match:
        return None, None
    year = 2000 + int(match.group(1))
    month = MONTHS.get(match.group(2).lower())
    return year, month


def _detect_econ_indicator(text):
    for pattern, indicator_id in ECON_INDICATOR_PATTERNS:
        if pattern.search(text or ""):
            return indicator_id
    return None


def _parse_econ_bucket(title, market=None):
    """
    Parse bucket type and numeric value from titles, subtitles, or group items.

    Returns (bucket_type, value) where bucket_type is one of:
    exact, above, below, at_least, at_most
    """
    market = market or {}
    combined = " ".join(filter(None, [
        title,
        market.get("yes_sub_title"),
        market.get("group_item_title"),
        market.get("rules_primary"),
    ]))

    exactly = EXACTLY_BUCKET.search(combined)
    if exactly:
        value = _parse_percent_value(exactly.group("value"))
        if value is not None:
            return "exact", value

    group_item = market.get("group_item_title") or ""
    if group_item:
        lowered_group = group_item.lower()
        if "or more" in lowered_group or group_item.strip().startswith("≥"):
            value = _parse_percent_value(group_item)
            if value is not None:
                return "at_least", value
        if "or less" in lowered_group or group_item.strip().startswith("≤"):
            value = _parse_percent_value(group_item)
            if value is not None:
                return "at_most", value
        value = _parse_percent_value(group_item)
        if value is not None:
            return "exact", value

    at_least = POLY_AT_LEAST_BUCKET.search(title or "")
    if at_least:
        value = _parse_percent_value(at_least.group("value"))
        if value is not None:
            return "at_least", value

    at_most = POLY_AT_MOST_BUCKET.search(title or "")
    if at_most:
        value = _parse_percent_value(at_most.group("value"))
        if value is not None:
            return "at_most", value

    exact_poly = POLY_EXACT_BUCKET.search(title or "")
    if exact_poly:
        value = _parse_percent_value(exact_poly.group("value"))
        if value is not None:
            return "exact", value

    rise_more = KALSHI_RISE_MORE_THAN.search(title or "")
    if rise_more:
        value = _parse_percent_value(rise_more.group("value"))
        if value is not None:
            return "above", value

    cpi = CPI_PATTERN.search(combined)
    if cpi:
        value = _parse_percent_value(cpi.group("pct"))
        if value is not None:
            direction = "below" if re.search(r"\b(below|under)\b", combined, re.I) else "above"
            return direction, value

    jobs = JOBS_ADDED.search(combined)
    if jobs:
        return "above", int(jobs.group("amount").replace(",", ""))

    unemp = UNEMPLOYMENT_ABOVE.search(combined)
    if unemp:
        return "above", float(unemp.group("pct"))

    threshold = extract_threshold(title)
    if threshold is not None:
        direction = "below" if re.search(r"\b(below|under|less than)\b", combined, re.I) else "above"
        return direction, threshold

    return None, None


def _canonical_bucket_outcome(bucket_type, value):
    if bucket_type is None or value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{bucket_type}_{value}"


def extract_economic_release_event_key(title, market=None):
    """
    Return ('econ_release', indicator_id, year, month) for bucket-style releases.

    Used to cluster CPI/NFP/U3 markets that share a release date and indicator.
    """
    market = market or {}
    event_title = market.get("event_title") or ""
    combined = f"{event_title} {title or ''} {market.get('rules_primary', '')}"

    indicator_id = _detect_econ_indicator(combined)
    if not indicator_id:
        return None

    month = _month_token(combined)
    year = _year_token(combined) or _year_from_date(market.get("end_date"))
    year = year or _year_from_date(market.get("close_time"))
    ticker_year, ticker_month = _month_year_from_event_ticker(market)
    year = year or ticker_year
    month = month or ticker_month

    if not month or not year:
        return None

    bucket_type, value = _parse_econ_bucket(title, market=market)
    if bucket_type is None and indicator_id in {"cpi_core_mom", "cpi_core_yoy", "cpi_yoy", "cpi_mom"}:
        # Kalshi bucket markets carry the strike only in yes_sub_title.
        bucket_type, value = _parse_econ_bucket("", market=market)
    if bucket_type is None:
        return None

    return ("econ_release", indicator_id, year, month)


def extract_economic_indicator_event_key(title, market=None):
    """
    Legacy econ_threshold keys for above/below markets without bucket structure.
    Bucket-style releases use extract_economic_release_event_key instead.
    """
    release = extract_economic_release_event_key(title, market=market)
    if release:
        return release

    combined = f"{title or ''} {(market or {}).get('rules_primary', '')}"
    lowered = combined.lower()

    month = _month_token(combined)
    year = _year_token(combined) or _year_from_date((market or {}).get("end_date"))
    year = year or _year_from_date((market or {}).get("close_time"))
    if not month or not year:
        return None

    direction = "above"
    if any(word in lowered for word in ("below", "under", "less than")):
        direction = "below"

    jobs = JOBS_ADDED.search(combined)
    if jobs or "jobs be added" in lowered or "payroll" in lowered:
        if jobs:
            value = int(jobs.group("amount").replace(",", ""))
        else:
            threshold = extract_threshold(title)
            if threshold is None:
                return None
            value = int(threshold)
        return ("econ_threshold", "nfp_jobs", year, month, direction, value)

    unemp = UNEMPLOYMENT_ABOVE.search(combined)
    if unemp or ("unemployment" in lowered and ("u-3" in lowered or "u3" in lowered)):
        if unemp:
            value = float(unemp.group("pct"))
        else:
            threshold = extract_threshold(title)
            if threshold is None:
                return None
            value = float(threshold)
        return ("econ_threshold", "u3_unemployment", year, month, direction, value)

    if "cpi" in lowered or "inflation" in lowered:
        cpi = CPI_PATTERN.search(combined)
        if cpi:
            value = float(cpi.group("pct"))
        else:
            threshold = extract_threshold(title)
            if threshold is None:
                return None
            value = float(threshold)
        return ("econ_threshold", "cpi", year, month, direction, value)

    if "gdp" in lowered:
        threshold = extract_threshold(title)
        if threshold is None:
            return None
        return ("econ_threshold", "gdp", year, month, direction, float(threshold))

    return None


def extract_threshold_event_key(title):
    """Return ('threshold', subject_key, threshold) for aligned strike markets."""
    threshold = extract_threshold(title)
    if threshold is None:
        return None

    lowered = (title or "").lower()
    subject_parts = []
    if "world cup final" in lowered and "ticketdata" in lowered:
        subject_parts = ["world_cup_final", "ticketdata"]
    elif "world cup final" in lowered:
        subject_parts = ["world_cup_final"]

    if not subject_parts:
        return None

    direction = "above"
    if any(word in lowered for word in ("below", "under")):
        direction = "below"

    return ("threshold", tuple(subject_parts), direction, threshold)


def extract_event_key(market):
    """
    Derive a canonical event key for clustering markets on the same real-world event.
    """
    title = market.get("market_question", "")
    event_title = market.get("event_title", "")

    central_bank = extract_central_bank_event_key(title, event_title=event_title, market=market)
    if central_bank:
        return central_bank

    economic = extract_economic_indicator_event_key(title, market=market)
    if economic:
        return economic

    esports = extract_esports_match_event_key(title, market=market)
    if esports:
        return esports

    golf = extract_golf_event_key(title, market=market)
    if golf:
        return golf

    sports = extract_sports_event_key(title, market=market)
    if sports:
        return sports

    threshold = extract_threshold_event_key(title)
    if threshold:
        return threshold

    politics = extract_politics_event_key(title, market=market)
    if politics:
        return politics

    crypto = extract_crypto_event_key(title, market=market)
    if crypto:
        return crypto

    sports_pm = extract_sports_pm_event_key(title, market=market)
    if sports_pm:
        return sports_pm

    legal = extract_legal_event_key(title, market=market)
    if legal:
        return legal

    return None


def normalize_economic_outcome(title, market=None):
    """Map econ release/threshold markets to canonical outcome labels."""
    market = market or {}
    event_key = market.get("event_key") or extract_economic_indicator_event_key(title, market=market)
    if not event_key:
        return None

    if event_key[0] == "econ_release":
        bucket_type, value = _parse_econ_bucket(title, market=market)
        if bucket_type is None:
            bucket_type, value = _parse_econ_bucket("", market=market)
        return _canonical_bucket_outcome(bucket_type, value)

    if event_key[0] != "econ_threshold":
        return None

    direction = event_key[4]
    value = event_key[5]
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{direction}_{value}"


def normalize_central_bank_outcome(title):
    """
    Map rate-decision market titles to canonical outcomes.

    Returns one of: hold, hike, cut, hike_small, hike_large, cut_small, cut_large
    """
    lowered = (title or "").lower()

    # Kalshi "hike/cut by 0bps" = no change.
    if re.search(r"\b(hike|cut)\s+rates?\s+by\s+0\s*bps\b", lowered):
        return "hold"
    if "maintain current rate" in lowered or "maintain" in lowered and "rate" in lowered:
        return "hold"

    kalshi_match = KALSHI_RATE_OUTCOME.search(lowered)
    if kalshi_match:
        phrase = kalshi_match.group(1).lower()
        if "maintain" in phrase:
            return "hold"
        if "hike 1-25" in phrase:
            return "hike_small"
        if "hike more than 25" in phrase:
            return "hike_large"
        if "cut 1-25" in phrase:
            return "cut_small"
        if "cut more than 25" in phrase:
            return "cut_large"

    if re.search(r"hike\s+rates?\s+by\s+25\s*bps", lowered):
        return "hike_small"
    if re.search(r"hike\s+rates?\s+by\s+>?25\s*bps", lowered) or "more than 25bps" in lowered:
        return "hike_large"
    if re.search(r"cut\s+rates?\s+by\s+25\s*bps", lowered):
        return "cut_small"
    if re.search(r"cut\s+rates?\s+by\s+>?25\s*bps", lowered):
        return "cut_large"

    if "no change" in lowered:
        return "hold"
    if re.search(r"(increase|hike).{0,30}50\+?\s*bps", lowered):
        return "hike_large"
    if re.search(r"(increase|hike).{0,30}25\s*bps", lowered):
        return "hike_small"
    if re.search(r"(decrease|cut).{0,30}50\+?\s*bps", lowered):
        return "cut_large"
    if re.search(r"(decrease|cut).{0,30}25\s*bps", lowered):
        return "cut_small"
    if "increase" in lowered or "hike" in lowered:
        return "hike"
    if "decrease" in lowered or "cut" in lowered:
        return "cut"

    poly_match = POLY_RATE_OUTCOME.search(lowered)
    if poly_match:
        word = poly_match.group(1).lower()
        if word == "no change":
            return "hold"
        if word == "increase":
            return "hike"
        if word == "decrease":
            return "cut"

    return None


def normalize_sports_outcome(title, market=None):
    """Map sports markets to canonical team/draw outcomes."""
    if market:
        yes_sub = market.get("yes_sub_title")
        if yes_sub:
            return normalize_entity(yes_sub)

        group_item = market.get("group_item_title")
        if group_item:
            return normalize_entity(group_item)

    lowered = (title or "").lower()
    if "end in a draw" in lowered or "draw" in lowered.split("?")[0][-20:]:
        return "draw"

    matchup = extract_matchup(title) or (market or {}).get("event_matchup")
    win_on_date = re.search(r"will\s+(.+?)\s+win\s+on\s+\d{4}-\d{2}-\d{2}", lowered)
    if win_on_date and matchup:
        return normalize_entity(win_on_date.group(1))

    return None


def normalize_golf_outcome(title, market=None):
    if market:
        if market.get("yes_sub_title"):
            return normalize_entity(market["yes_sub_title"])
        if market.get("group_item_title"):
            return normalize_entity(market["group_item_title"])

    match = GOLF_WINNER.search(title or "")
    if match:
        return normalize_entity(match.group(1))

    return None


def normalize_esports_outcome(title, market=None):
    if market and market.get("yes_sub_title"):
        return normalize_entity(market["yes_sub_title"])
    if market and market.get("group_item_title"):
        return normalize_entity(market["group_item_title"])

    matchup = extract_matchup(title) or (market or {}).get("event_matchup")
    if not matchup:
        return None

    lowered = (title or "").lower()
    for team in matchup:
        if team in lowered and "win" in lowered:
            return team

    return None


def normalize_market_outcome(market):
    """Return canonical outcome label for a market within its event cluster."""
    title = market.get("market_question", "")
    event_key = market.get("event_key") or extract_event_key(market)

    if not event_key:
        return None

    event_type = event_key[0]
    if event_type == "central_bank":
        return normalize_central_bank_outcome(title)
    if event_type in {"econ_threshold", "econ_release"}:
        return normalize_economic_outcome(title, market=market)
    if event_type == "sports_match":
        return normalize_sports_outcome(title, market=market)
    if event_type == "esports_match":
        return normalize_esports_outcome(title, market=market)
    if event_type == "golf_tournament":
        return normalize_golf_outcome(title, market=market)
    if event_type == "threshold":
        direction = event_key[2]
        return f"{direction}_{event_key[3]}"
    if event_type == "election":
        return normalize_politics_outcome(title, market=market)
    if event_type == "crypto_threshold":
        return normalize_crypto_outcome(title, market=market)
    if event_type == "sports_pm":
        return normalize_sports_pm_outcome(title, market=market)
    if event_type == "legal_outcome":
        return normalize_legal_outcome(title, market=market)

    return None


# Outcomes that represent the same resolution on both platforms (safe for 2-leg arb).
EQUIVALENT_OUTCOME_GROUPS = [
    {"hold"},
    {"hike_small"},
    {"hike_large"},
    {"cut_small"},
    {"cut_large"},
    {"draw"},
    {"above"},
    {"below"},
]

# Map aggregate Polymarket buckets to Kalshi sub-buckets (for display only, not 2-leg arb).
RELATED_OUTCOME_GROUPS = [
    {"hike", "hike_small", "hike_large"},
    {"cut", "cut_small", "cut_large"},
]


def outcomes_are_equivalent(outcome_a, outcome_b):
    """True when two canonical outcomes resolve identically."""
    if not outcome_a or not outcome_b:
        return False
    if outcome_a == outcome_b:
        return True

    # Never treat aggregate hike/cut as equivalent to sized buckets.
    sized = {"hike_small", "hike_large", "cut_small", "cut_large", "hold"}
    if outcome_a in sized and outcome_b in {"hike", "cut"}:
        return False
    if outcome_b in sized and outcome_a in {"hike", "cut"}:
        return False

    for group in EQUIVALENT_OUTCOME_GROUPS:
        if outcome_a in group and outcome_b in group:
            return True

    return False


def attach_event_metadata(market):
    """Attach event_key and canonical_outcome to a normalized market dict."""
    market["event_key"] = extract_event_key(market)
    market["canonical_outcome"] = normalize_market_outcome(market)
    return market
