# Canonical event keys and outcomes for US election / politics markets.
import re

from entity_matching import normalize_entity

US_STATE_NAME_TO_CODE = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy", "district of columbia": "dc",
}

US_STATE_CODES = tuple(sorted(set(US_STATE_NAME_TO_CODE.values())))

YEAR_IN_TEXT = re.compile(r"\b(20\d{2})\b")

KALSHI_SENATE_TICKER = re.compile(r"^SENATE(?P<code>[A-Z]{2})-(?P<yy>\d{2})-[RD]$", re.I)
KALSHI_HOUSE_TICKER = re.compile(r"^HOUSE(?P<code>[A-Z]{2})-(?P<yy>\d{2})-[RD]$", re.I)
KALSHI_GOV_TICKER = re.compile(r"^GOV(?P<code>[A-Z]{2})-(?P<yy>\d{2})-[RD]$", re.I)

SENATE_RACE_KALSHI = re.compile(
    r"will (?:the )?(?P<party>republicans?|democrats?|democratics?|gop)\s+win the senate race in (?P<state>[a-z .]+?)\??$",
    re.I,
)
SENATE_RACE_POLY = re.compile(
    r"will the (?P<party>republicans?|democrats?|gop)\s+win the (?P<state>[a-z .]+?)\s+senate race in (?P<year>20\d{2})",
    re.I,
)
HOUSE_RACE_KALSHI = re.compile(
    r"will (?:the )?(?P<party>republicans?|democrats?|gop)\s+win the house race in (?P<state>[a-z .]+?)\??$",
    re.I,
)
HOUSE_RACE_POLY = re.compile(
    r"will the (?P<party>republicans?|democrats?|gop)\s+win the (?P<state>[a-z .]+?)\s+house race in (?P<year>20\d{2})",
    re.I,
)
CHAMBER_CONTROL = re.compile(
    r"will (?:the )?(?P<party>republicans?|democrats?|gop)\s+(?:win|control|have control of) (?:the )?"
    r"(?P<chamber>senate|house)(?:\s+in\s+(?P<year>20\d{2}))?",
    re.I,
)
GOV_RACE_POLY = re.compile(
    r"will (?P<candidate>.+?)\s+win the (?P<year>20\d{2})\s+(?P<state>[a-z .]+?)\s+"
    r"(?P<office>governor|gubernatorial)(?:\s+(?P<party>democratic|republican))?\s+primary",
    re.I,
)
GOV_RACE_KALSHI = re.compile(
    r"will (?P<candidate>.+?)\s+win (?:the )?(?P<state>[a-z .]+?)\s+governor(?:'s|ship)?\s+(?:race|election)",
    re.I,
)
ENDORSEMENT = re.compile(
    r"will (?P<endorser>.+?)\s+endorse (?P<candidate>.+?)\s+in (?P<state>[a-z .]+?)\s+"
    r"(?P<office>gubernatorial|senate|house)",
    re.I,
)


def _normalize_state(text):
    if not text:
        return None
    cleaned = normalize_entity(text.strip())
    if len(cleaned) == 2 and cleaned in US_STATE_CODES:
        return cleaned
    return US_STATE_NAME_TO_CODE.get(cleaned)


def _normalize_party(text):
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"republican", "republicans", "gop"}:
        return "republican"
    if lowered in {"democrat", "democrats", "democratic", "democratics"}:
        return "democrat"
    return None


def _year_from_text(*texts, market=None):
    for text in texts:
        if not text:
            continue
        match = YEAR_IN_TEXT.search(text)
        if match:
            return int(match.group(1))
    if market:
        for field in ("end_date", "close_time"):
            value = market.get(field)
            if value:
                match = YEAR_IN_TEXT.search(str(value))
                if match:
                    return int(match.group(1))
    return None


def _party_from_ticker(ticker):
    if not ticker:
        return None
    if ticker.upper().endswith("-R"):
        return "republican"
    if ticker.upper().endswith("-D"):
        return "democrat"
    return None


def _state_from_ticker(ticker):
    for pattern in (KALSHI_SENATE_TICKER, KALSHI_HOUSE_TICKER, KALSHI_GOV_TICKER):
        match = pattern.match(ticker or "")
        if match:
            return match.group("code").lower()
    return None


def _year_from_ticker(ticker):
    for pattern in (KALSHI_SENATE_TICKER, KALSHI_HOUSE_TICKER, KALSHI_GOV_TICKER):
        match = pattern.match(ticker or "")
        if match:
            return 2000 + int(match.group("yy"))
    return None


def extract_politics_event_key(title, market=None):
    """
    Return a canonical politics event key tuple, or None.

    Examples:
      ('election', 'senate_race', 'id', 2026)
      ('election', 'chamber_control', 'senate', 2026)
    """
    market = market or {}
    combined = f"{market.get('event_title', '')} {title or ''}"
    ticker = market.get("ticker") or market.get("event_ticker") or ""
    state_code = _state_from_ticker(ticker)
    year = _year_from_ticker(ticker) or _year_from_text(combined, market=market) or 2026

    match = SENATE_RACE_POLY.search(combined)
    if match:
        state_code = _normalize_state(match.group("state")) or state_code
        year = int(match.group("year"))
        if state_code:
            return ("election", "senate_race", state_code, year)

    match = SENATE_RACE_KALSHI.search(combined)
    if match:
        state_code = _normalize_state(match.group("state")) or state_code
        if state_code:
            return ("election", "senate_race", state_code, year)

    match = HOUSE_RACE_POLY.search(combined)
    if match:
        state_code = _normalize_state(match.group("state")) or state_code
        year = int(match.group("year"))
        if state_code:
            return ("election", "house_race", state_code, year)

    match = HOUSE_RACE_KALSHI.search(combined)
    if match:
        state_code = _normalize_state(match.group("state")) or state_code
        if state_code:
            return ("election", "house_race", state_code, year)

    match = CHAMBER_CONTROL.search(combined)
    if match:
        chamber = match.group("chamber").lower()
        year = int(match.group("year")) if match.group("year") else year
        return ("election", "chamber_control", chamber, year)

    if state_code and ticker.upper().startswith("SENATE"):
        return ("election", "senate_race", state_code, year)
    if state_code and ticker.upper().startswith("HOUSE"):
        return ("election", "house_race", state_code, year)
    if state_code and ticker.upper().startswith("GOV"):
        return ("election", "governor_race", state_code, year)

    match = GOV_RACE_POLY.search(combined)
    if match:
        state_code = _normalize_state(match.group("state"))
        if state_code:
            return ("election", "governor_primary", state_code, int(match.group("year")))

    match = GOV_RACE_KALSHI.search(combined)
    if match:
        state_code = _normalize_state(match.group("state"))
        if state_code:
            return ("election", "governor_race", state_code, year)

    match = ENDORSEMENT.search(combined)
    if match:
        state_code = _normalize_state(match.group("state"))
        office = match.group("office").lower()
        if state_code:
            endorser = normalize_entity(match.group("endorser"))
            candidate = normalize_entity(match.group("candidate"))
            return ("election", "endorsement", office, state_code, endorser, candidate, year)

    return None


def normalize_politics_outcome(title, market=None):
    """Map politics markets to canonical party/candidate outcomes."""
    market = market or {}
    event_key = market.get("event_key") or extract_politics_event_key(title, market=market)
    if not event_key or event_key[0] != "election":
        return None

    event_type = event_key[1]
    combined = f"{title or ''} {market.get('yes_sub_title', '')} {market.get('group_item_title', '')}"
    ticker = market.get("ticker") or ""

    party = _party_from_ticker(ticker)
    if not party:
        for pattern in (SENATE_RACE_POLY, SENATE_RACE_KALSHI, HOUSE_RACE_POLY, HOUSE_RACE_KALSHI, CHAMBER_CONTROL):
            match = pattern.search(combined)
            if match and match.groupdict().get("party"):
                party = _normalize_party(match.group("party"))
                if party:
                    break

    if party and event_type in {"senate_race", "house_race", "chamber_control", "governor_race"}:
        if event_type == "chamber_control":
            return f"{party}_control"
        return f"{party}_win"

    if event_type == "governor_primary":
        candidate = market.get("group_item_title") or market.get("yes_sub_title")
        if candidate:
            return normalize_entity(candidate)
        match = GOV_RACE_POLY.search(combined)
        if match:
            return normalize_entity(match.group("candidate"))

    if event_type == "endorsement":
        return "yes"

    if market.get("yes_sub_title"):
        return normalize_entity(market["yes_sub_title"])
    if market.get("group_item_title"):
        return normalize_entity(market["group_item_title"])

    return None
