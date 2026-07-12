# Match team names between Kalshi titles and sportsbook events.
import re

from entity_matching import extract_matchup, normalize_entity

TEAM_ALIASES = {
    "man city": "manchester city",
    "man united": "manchester united",
    "psg": "paris saint germain",
    "la clippers": "los angeles clippers",
    "la lakers": "los angeles lakers",
}


def normalize_team(name):
    text = normalize_entity(name or "")
    text = TEAM_ALIASES.get(text, text)
    text = re.sub(r"\b(fc|sc|cf|afc|the)\b", "", text).strip()
    return text


def team_match_score(name_a, name_b):
    """Return 0-1 similarity score for two team names."""
    a = normalize_team(name_a)
    b = normalize_team(name_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9

    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return 0.0

    shared = a_tokens & b_tokens
    if len(shared) >= 2:
        return 0.85
    if len(shared) == 1 and max(len(a_tokens), len(b_tokens)) <= 2:
        return 0.75
    return 0.0


def match_teams_to_event(team_a, team_b, event):
    """
    Return True if Kalshi teams align with an odds API event (home/away either order).
    """
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    if not home or not away:
        return False

    score_direct = (
        team_match_score(team_a, home) + team_match_score(team_b, away)
    ) / 2
    score_swap = (
        team_match_score(team_a, away) + team_match_score(team_b, home)
    ) / 2
    return max(score_direct, score_swap) >= 0.75


def find_matching_event(kalshi_market, odds_events):
    """Find the best matching sportsbook event for a Kalshi sports market."""
    title = kalshi_market.get("market_question", "")
    matchup = extract_matchup(title)
    if not matchup and kalshi_market.get("event_matchup"):
        matchup = kalshi_market["event_matchup"]

    if not matchup:
        return None

    team_a, team_b = matchup
    best = None
    best_score = 0.0

    for event in odds_events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        score_direct = (
            team_match_score(team_a, home) + team_match_score(team_b, away)
        ) / 2
        score_swap = (
            team_match_score(team_a, away) + team_match_score(team_b, home)
        ) / 2
        score = max(score_direct, score_swap)
        if score > best_score:
            best_score = score
            best = event

    if best_score >= 0.75:
        return best, best_score
    return None


def kalshi_outcome_team(kalshi_market):
    """Which team/outcome the Kalshi YES contract refers to."""
    if kalshi_market.get("yes_sub_title"):
        return normalize_team(kalshi_market["yes_sub_title"])

    title = kalshi_market.get("market_question", "")
    matchup = extract_matchup(title)
    if not matchup:
        return None

    lowered = title.lower()
    for team in matchup:
        if team in lowered and "win" in lowered:
            return team
    return None
