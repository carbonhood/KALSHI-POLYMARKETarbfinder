# Canonical event keys for sports prediction-market game winners.
import re

from entity_matching import extract_matchup, normalize_entity, normalize_outcome

SPORTS_WINNER_POLY = re.compile(
    r"will (?:the )?(?P<team>.+?)\s+win(?:\s+on\s+(?P<date>\d{4}-\d{2}-\d{2}))?",
    re.I,
)
KALSHI_SPORTS_TICKER = re.compile(
    r"^(?P<league>[A-Z]+)(?P<code>[A-Z]{2,8})-\d+",
    re.I,
)


def _game_date_from_market(market):
    for field in ("occurrence_datetime", "close_time", "end_date"):
        value = (market or {}).get(field)
        if value:
            return str(value)[:10]
    match = SPORTS_WINNER_POLY.search((market or {}).get("market_question", ""))
    if match and match.group("date"):
        return match.group("date")
    return None


def extract_sports_pm_event_key(title, market=None):
    """
    Return ('sports_pm', league_or_sport, team_a, team_b, date) for head-to-head winners.
    """
    market = market or {}
    title = title or market.get("market_question", "")
    matchup = extract_matchup(title) or market.get("event_matchup")
    if not matchup:
        return None

    game_date = _game_date_from_market(market)
    if not game_date:
        return None

    league = "general"
    ticker = market.get("ticker") or market.get("event_ticker") or ""
    ticker_match = KALSHI_SPORTS_TICKER.match(ticker)
    if ticker_match:
        league = ticker_match.group("league").lower()

    return ("sports_pm", league, matchup[0], matchup[1], game_date)


def normalize_sports_pm_outcome(title, market=None):
    market = market or {}
    if market.get("yes_sub_title"):
        return normalize_entity(market["yes_sub_title"])
    if market.get("group_item_title"):
        return normalize_entity(market["group_item_title"])

    matchup = extract_matchup(title) or market.get("event_matchup")
    if not matchup:
        return None

    win_match = SPORTS_WINNER_POLY.search(title)
    if win_match:
        return normalize_entity(win_match.group("team"))

    return normalize_outcome(title)
