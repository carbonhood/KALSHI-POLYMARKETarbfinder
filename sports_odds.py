# Fetch sports odds from The Odds API (aggregates Betfair, Pinnacle, US books, etc.).
import json
import os
from pathlib import Path

import requests

from config import (
    ODDS_API_BASE,
    ODDS_API_MARKETS,
    ODDS_API_ODDS_FORMAT,
    ODDS_API_REGIONS,
    MAX_SPORTS_TO_SCAN,
    SPORTS_PRIORITY_KEYS,
)

ODDS_CACHE_PATH = Path("sports_odds.json")


def get_api_key():
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if key:
        return key

    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "ODDS_API_KEY":
                return value.strip().strip('"').strip("'")
    return ""


def list_sports(api_key=None):
    """Return all sports (active and inactive) from The Odds API."""
    key = api_key or get_api_key()
    if not key:
        raise ValueError("ODDS_API_KEY environment variable is not set.")

    response = requests.get(f"{ODDS_API_BASE}/sports", params={"apiKey": key}, timeout=30)
    response.raise_for_status()
    return response.json()


def pick_sports_to_scan(api_key=None):
    """
    Choose sport keys to scan for h2h arbs.

    Prefers in-season sports from SPORTS_PRIORITY_KEYS, then fills with other active sports.
    """
    sports = list_sports(api_key)
    active = {item["key"]: item for item in sports if item.get("active")}

    chosen = []
    for key in SPORTS_PRIORITY_KEYS:
        if key in active and key not in chosen:
            chosen.append(key)
        if len(chosen) >= MAX_SPORTS_TO_SCAN:
            return chosen

    for key, item in active.items():
        if key in chosen:
            continue
        if item.get("has_outrights") and "soccer" not in key:
            continue
        chosen.append(key)
        if len(chosen) >= MAX_SPORTS_TO_SCAN:
            break

    return chosen


def fetch_odds(sport_key, api_key=None, regions=None, markets=None):
    """Fetch h2h odds for one sport across configured bookmaker regions."""
    key = api_key or get_api_key()
    if not key:
        raise ValueError("ODDS_API_KEY environment variable is not set.")

    params = {
        "apiKey": key,
        "regions": regions or ODDS_API_REGIONS,
        "markets": markets or ODDS_API_MARKETS,
        "oddsFormat": ODDS_API_ODDS_FORMAT,
    }
    response = requests.get(f"{ODDS_API_BASE}/sports/{sport_key}/odds", params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def fetch_all_odds(api_key=None):
    """Fetch odds for all selected sports and cache to sports_odds.json."""
    key = api_key or get_api_key()
    sport_keys = pick_sports_to_scan(key)
    payload = {
        "sport_keys": sport_keys,
        "regions": ODDS_API_REGIONS,
        "markets": ODDS_API_MARKETS,
        "events": [],
    }

    for sport_key in sport_keys:
        events = fetch_odds(sport_key, api_key=key)
        for event in events:
            event["_sport_key"] = sport_key
        payload["events"].extend(events)
        print(f"  {sport_key}: {len(events)} events")

    with open(ODDS_CACHE_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    print(f"Saved {len(payload['events'])} events to {ODDS_CACHE_PATH}")
    return payload


def load_cached_odds():
    if not ODDS_CACHE_PATH.exists():
        return {"events": []}
    with open(ODDS_CACHE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)
