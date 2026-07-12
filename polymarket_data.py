# Fetches raw Polymarket event data and converts it into a normalized market list.
import json
import re

import requests

from config import (
    ENABLED_CATEGORIES,
    GEOPOLITICS_POLYMARKET_SEARCHES,
    GEOPOLITICS_POLYMARKET_TAGS,
    KALSHI_POLY_SEARCH_LIMIT,
    MACRO_MAX_DAYS_TO_RESOLUTION,
    MACRO_POLYMARKET_MAX_EVENTS,
    MACRO_POLYMARKET_SEARCHES,
    MACRO_POLYMARKET_TAGS,
    MAX_DAYS_TO_RESOLUTION,
    POLITICS_POLYMARKET_SEARCHES,
    POLITICS_POLYMARKET_TAGS,
    CRYPTO_POLYMARKET_SEARCHES,
    CRYPTO_POLYMARKET_TAGS,
    LEGAL_POLYMARKET_SEARCHES,
    LEGAL_POLYMARKET_TAGS,
    SPORTS_PM_POLYMARKET_SEARCHES,
    SPORTS_PM_POLYMARKET_TAGS,
    POLYMARKET_MAX_EVENTS,
    POLYMARKET_PAGE_LIMIT,
    POLYMARKET_PRIORITY_SEARCHES,
    scan_horizon_days,
)
from entity_matching import extract_matchup
from fees import polymarket_fee_rate_from_market
from market_utils import days_until_resolution, is_tradable_binary_book, polymarket_horizon_dates, within_resolution_horizon
from market_liquidity import polymarket_activity_from_gamma
from polymarket_clob import fetch_buy_prices, prices_from_tokens

BASE_URL = "https://gamma-api.polymarket.com/events"
SEARCH_URL = "https://gamma-api.polymarket.com/public-search"

# Shared list used by other modules after extract_polymarket_details() runs.
clean_markets_polymarket = []


def _fetch_event_pages(params, max_events):
    """Paginate Polymarket /events until max_events or no more pages."""
    events = []
    offset = 0

    while len(events) < max_events:
        page_params = {**params, "limit": POLYMARKET_PAGE_LIMIT, "offset": offset}
        response = requests.get(BASE_URL, params=page_params, timeout=60)
        if response.status_code == 422:
            break
        response.raise_for_status()
        page_data = response.json()
        if not isinstance(page_data, list):
            raise ValueError(f"Unexpected Polymarket API response: {page_data}")

        events.extend(page_data)
        if len(page_data) < POLYMARKET_PAGE_LIMIT:
            break
        offset += POLYMARKET_PAGE_LIMIT

    return events[:max_events]


def _load_saved_events():
    with open("polymarket_data.json", "r", encoding="utf-8") as file:
        data = json.load(file)
    return list(_iter_polymarket_events(data))


def _save_events(events, metadata):
    payload = {
        "fetch_mode": "short_term_events",
        **metadata,
        "events": events,
    }
    with open("polymarket_data.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)
    return payload


def fetch_prices(max_days=MAX_DAYS_TO_RESOLUTION):
    """
    Download active Polymarket events that end within max_days.

    Fetches sports-tagged events first, then fills the remaining quota with
    other near-term events so game markets are not buried behind politics.
    """
    end_date_min, end_date_max = polymarket_horizon_dates(max_days)
    base_params = {
        "active": "true",
        "closed": "false",
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
    }

    sports_events = _fetch_event_pages({**base_params, "tag_slug": "sports"}, POLYMARKET_MAX_EVENTS)
    seen_ids = {event.get("id") for event in sports_events}
    remaining = max(0, POLYMARKET_MAX_EVENTS - len(sports_events))

    general_events = []
    if remaining:
        general_events = _fetch_event_pages(base_params, remaining + len(seen_ids))
        general_events = [
            event for event in general_events
            if event.get("id") not in seen_ids
        ][:remaining]

    polymarket_data = sports_events + general_events
    metadata = {
        "max_days_to_resolution": max_days,
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
        "sports_event_count": len(sports_events),
        "general_event_count": len(general_events),
        "search_event_count": 0,
    }
    _save_events(polymarket_data, metadata)
    print(
        f"Polymarket data saved to polymarket_data.json "
        f"({len(polymarket_data)} events: {len(sports_events)} sports, "
        f"{len(general_events)} other; ending by {end_date_max})"
    )
    return polymarket_data


MACRO_SEARCH_QUERIES = MACRO_POLYMARKET_SEARCHES


def _merge_events(existing, new_events):
    seen = {event.get("id") for event in existing}
    merged = list(existing)
    added = 0
    for event in new_events:
        if event.get("id") in seen:
            continue
        seen.add(event.get("id"))
        merged.append(event)
        added += 1
    return merged, added


def fetch_all_category_polymarket_data(max_days=None):
    """Fetch Polymarket events for all enabled categories."""
    if max_days is None:
        max_days = scan_horizon_days()
    end_date_min, end_date_max = polymarket_horizon_dates(max_days)
    base_params = {
        "active": "true",
        "closed": "false",
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
    }

    tag_map = {
        "macro": (MACRO_POLYMARKET_TAGS, MACRO_POLYMARKET_SEARCHES),
        "politics_elections": (POLITICS_POLYMARKET_TAGS, POLITICS_POLYMARKET_SEARCHES),
        "geopolitics": (GEOPOLITICS_POLYMARKET_TAGS, GEOPOLITICS_POLYMARKET_SEARCHES),
        "sports_pm": (SPORTS_PM_POLYMARKET_TAGS, SPORTS_PM_POLYMARKET_SEARCHES),
        "crypto": (CRYPTO_POLYMARKET_TAGS, CRYPTO_POLYMARKET_SEARCHES),
        "legal": (LEGAL_POLYMARKET_TAGS, LEGAL_POLYMARKET_SEARCHES),
    }

    events = []
    for category in ENABLED_CATEGORIES:
        if len(events) >= POLYMARKET_MAX_EVENTS:
            break
        tags, searches = tag_map.get(category, ([], []))
        for tag in tags:
            if len(events) >= POLYMARKET_MAX_EVENTS:
                break
            remaining = POLYMARKET_MAX_EVENTS - len(events)
            tag_events = _fetch_event_pages(
                {**base_params, "tag_slug": tag},
                remaining,
            )
            events, _ = _merge_events(events, tag_events)
        seen_ids = {event.get("id") for event in events}
        for query in searches:
            if len(events) >= POLYMARKET_MAX_EVENTS:
                break
            response = requests.get(
                SEARCH_URL,
                params={"q": query, "limit_per_type": 15, "events_status": "active"},
                timeout=30,
            )
            response.raise_for_status()
            for event in response.json().get("events", []):
                if len(events) >= POLYMARKET_MAX_EVENTS:
                    break
                if event.get("id") in seen_ids:
                    continue
                end_date = event.get("endDate")
                if not within_resolution_horizon(end_date, max_days):
                    continue
                seen_ids.add(event.get("id"))
                events.append(event)

    events = events[:POLYMARKET_MAX_EVENTS]

    metadata = {
        "fetch_mode": "category_scan",
        "enabled_categories": list(ENABLED_CATEGORIES),
        "max_days_to_resolution": max_days,
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
        "event_count": len(events),
    }
    _save_events(events, metadata)
    print(
        f"Polymarket category data saved ({len(events)} events, "
        f"categories={list(ENABLED_CATEGORIES)}, ending by {end_date_max})"
    )
    return events


def fetch_macro_polymarket_data(max_days=MACRO_MAX_DAYS_TO_RESOLUTION):
    """
    Macro-only Polymarket fetch: finance/economics tags + targeted searches.

    Does not pull sports-tagged events.
    """
    end_date_min, end_date_max = polymarket_horizon_dates(max_days)
    base_params = {
        "active": "true",
        "closed": "false",
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
    }

    events = []
    for tag in MACRO_POLYMARKET_TAGS:
        tag_events = _fetch_event_pages(
            {**base_params, "tag_slug": tag},
            MACRO_POLYMARKET_MAX_EVENTS,
        )
        events, _ = _merge_events(events, tag_events)

    seen_ids = {event.get("id") for event in events}
    search_added = 0
    for query in MACRO_POLYMARKET_SEARCHES:
        response = requests.get(
            SEARCH_URL,
            params={"q": query, "limit_per_type": 15, "events_status": "active"},
            timeout=30,
        )
        response.raise_for_status()
        for event in response.json().get("events", []):
            if event.get("id") in seen_ids:
                continue
            end_date = event.get("endDate")
            if not within_resolution_horizon(end_date, max_days):
                continue
            seen_ids.add(event.get("id"))
            events.append(event)
            search_added += 1

    metadata = {
        "fetch_mode": "macro_only",
        "max_days_to_resolution": max_days,
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
        "macro_event_count": len(events),
        "macro_search_added": search_added,
    }
    _save_events(events, metadata)
    print(
        f"Polymarket macro data saved ({len(events)} events, ending by {end_date_max})"
    )
    return events


def fetch_macro_events(max_days=MACRO_MAX_DAYS_TO_RESOLUTION):
    """Fetch finance/macro-tagged Polymarket events on a longer horizon."""
    end_date_min, end_date_max = polymarket_horizon_dates(max_days)
    base_params = {
        "active": "true",
        "closed": "false",
        "end_date_min": end_date_min,
        "end_date_max": end_date_max,
    }

    macro_events = []
    for tag in MACRO_POLYMARKET_TAGS:
        tag_events = _fetch_event_pages(
            {**base_params, "tag_slug": tag},
            MACRO_POLYMARKET_MAX_EVENTS,
        )
        macro_events, _ = _merge_events(macro_events, tag_events)

    events = _load_saved_events()
    events, tag_added = _merge_events(events, macro_events)

    search_added = 0
    seen_ids = {event.get("id") for event in events}
    for query in MACRO_SEARCH_QUERIES:
        response = requests.get(
            SEARCH_URL,
            params={"q": query, "limit_per_type": 10, "events_status": "active"},
            timeout=30,
        )
        response.raise_for_status()
        for event in response.json().get("events", []):
            if event.get("id") in seen_ids:
                continue
            end_date = event.get("endDate")
            if not within_resolution_horizon(end_date, max_days):
                continue
            seen_ids.add(event.get("id"))
            events.append(event)
            search_added += 1

    with open("polymarket_data.json", "r", encoding="utf-8") as file:
        payload = json.load(file)
    payload["events"] = events
    payload["macro_event_count"] = tag_added + search_added
    payload["macro_end_date_max"] = end_date_max
    with open("polymarket_data.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    print(
        f"Polymarket macro supplement added {tag_added + search_added} events "
        f"(ending by {end_date_max})"
    )
    return tag_added + search_added


def build_kalshi_search_queries(kalshi_markets, limit=KALSHI_POLY_SEARCH_LIMIT):
    """
    Build Polymarket search queries from Kalshi titles.

    This helps surface Polymarket events that share entities with Kalshi but
    may not appear in the first pages of the events feed.
    """
    queries = []
    seen = set()

    for market in kalshi_markets:
        title = market.get("market_question") or market.get("title", "")
        candidates = []

        matchup = extract_matchup(title)
        if matchup:
            candidates.append(f"{matchup[0]} vs {matchup[1]}")

        if "bank of korea" in title.lower():
            candidates.append("Bank of Korea")
        if "federal reserve" in title.lower() or "fomc" in title.lower():
            candidates.append("Federal Reserve FOMC")
        if "unemployment" in title.lower() or "u-3" in title.lower():
            candidates.append("unemployment rate")
        if "jobs be added" in title.lower() or "payroll" in title.lower():
            candidates.append("nonfarm payroll")
        if "cpi" in title.lower() or "inflation" in title.lower():
            candidates.append("CPI inflation")
        if "gdp" in title.lower():
            candidates.append("GDP")
        if "senate" in title.lower() and "race" in title.lower():
            candidates.append("Senate race 2026")
            state_match = re.search(
                r"senate race in ([a-z .]+?)\??$|win the ([a-z .]+?) senate race",
                title.lower(),
            )
            if state_match:
                state = (state_match.group(1) or state_match.group(2) or "").strip().title()
                if state:
                    candidates.append(f"{state} Senate race 2026")
                    candidates.append(f"Republicans win {state} Senate")
        if "house" in title.lower() and "race" in title.lower():
            state_match = re.search(r"house race in ([a-z .]+?)\??$", title.lower())
            if state_match:
                state = state_match.group(1).strip().title()
                candidates.append(f"{state} House race 2026")
        if "republicans" in title.lower() and "senate" in title.lower():
            candidates.append("Republicans win Senate")
        if "democrats" in title.lower() and "senate" in title.lower():
            candidates.append("Democrats win Senate")

        if "call of duty" in title.lower() or "gentle mates" in title.lower():
            candidates.append("Call of Duty Gentle Mates Toronto KOI")
        if "open championship" in title.lower():
            candidates.append("The Open Championship")

        compact = re.sub(r"\s+", " ", title).strip(" ?")
        if len(compact) >= 12:
            candidates.append(compact[:80])

        for candidate in candidates:
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append(candidate)
            if len(queries) >= limit:
                return queries

    return queries


def supplement_from_kalshi_searches(kalshi_markets, max_days=MACRO_MAX_DAYS_TO_RESOLUTION):
    """Search Polymarket for Kalshi-derived queries and merge new events."""
    if not kalshi_markets:
        return 0

    events = _load_saved_events()
    seen_ids = {event.get("id") for event in events}
    queries = build_kalshi_search_queries(kalshi_markets)
    added = 0

    for query in queries:
        response = requests.get(
            SEARCH_URL,
            params={
                "q": query,
                "limit_per_type": 5,
                "events_status": "active",
            },
            timeout=30,
        )
        response.raise_for_status()
        for event in response.json().get("events", []):
            if event.get("id") in seen_ids:
                continue

            end_date = event.get("endDate")
            if not within_resolution_horizon(end_date, max_days):
                continue

            seen_ids.add(event.get("id"))
            events.append(event)
            added += 1

    if added:
        with open("polymarket_data.json", "r", encoding="utf-8") as file:
            payload = json.load(file)
        payload["events"] = events
        payload["search_event_count"] = payload.get("search_event_count", 0) + added
        with open("polymarket_data.json", "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4)

    print(f"Polymarket search supplement added {added} events from {len(queries)} Kalshi queries")
    return added


def fetch_priority_searches(max_days=MACRO_MAX_DAYS_TO_RESOLUTION):
    """Search Polymarket for high-overlap topics (esports, golf, macro)."""
    events = _load_saved_events()
    seen_ids = {event.get("id") for event in events}
    added = 0

    for query in POLYMARKET_PRIORITY_SEARCHES:
        response = requests.get(
            SEARCH_URL,
            params={"q": query, "limit_per_type": 10, "events_status": "active"},
            timeout=30,
        )
        response.raise_for_status()
        for event in response.json().get("events", []):
            if event.get("id") in seen_ids:
                continue
            end_date = event.get("endDate")
            if not within_resolution_horizon(end_date, max_days):
                continue
            seen_ids.add(event.get("id"))
            events.append(event)
            added += 1

    with open("polymarket_data.json", "r", encoding="utf-8") as file:
        payload = json.load(file)
    payload["events"] = events
    payload["priority_search_count"] = payload.get("priority_search_count", 0) + added
    with open("polymarket_data.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    print(f"Polymarket priority search added {added} events")
    return added


def _iter_polymarket_events(data):
    if isinstance(data, list):
        yield from data
        return
    yield from data.get("events", [])


def _market_end_date(event, market):
    return market.get("endDate") or market.get("endDateIso") or event.get("endDate")


def _parse_token_ids(market):
    raw = market.get("clobTokenIds")
    if not raw:
        return None

    token_ids = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(token_ids, list) or len(token_ids) < 2:
        return None

    return str(token_ids[0]), str(token_ids[1])


def _event_matchup(event):
    """Find a shared A-vs-B matchup from any market in a Polymarket event."""
    for market in event.get("markets", []):
        matchup = extract_matchup(market.get("question", ""))
        if matchup:
            return matchup
    return None


def _collect_market_candidates(data, max_days, macro_days=MACRO_MAX_DAYS_TO_RESOLUTION):
    """Collect tradable markets and the CLOB token IDs needed for best-ask pricing."""
    candidates = []
    token_ids = []

    for event in _iter_polymarket_events(data):
        event_tags = event.get("tags", [])
        event_matchup = _event_matchup(event)
        event_title = event.get("title", "")
        event_id = event.get("id")
        for market in event.get("markets", []):
            end_date = _market_end_date(event, market)
            if not (
                within_resolution_horizon(end_date, max_days)
                or within_resolution_horizon(end_date, macro_days)
            ):
                continue

            market_question = market.get("question")
            if not market_question:
                continue

            tokens = _parse_token_ids(market)
            if tokens is None:
                continue

            yes_token_id, no_token_id = tokens
            token_ids.extend([yes_token_id, no_token_id])
            candidates.append({
                "event": event,
                "event_tags": event_tags,
                "event_matchup": event_matchup,
                "event_title": event_title,
                "event_id": event_id,
                "event_description": event.get("description") or "",
                "event_resolution_source": event.get("resolutionSource") or "",
                "market": market,
                "market_question": market_question,
                "end_date": end_date,
                "yes_token_id": yes_token_id,
                "no_token_id": no_token_id,
            })

    return candidates, token_ids


def extract_polymarket_details(max_days=None):
    """
    Read polymarket_data.json and build clean_markets_polymarket using CLOB
    best-ask prices for both YES and NO legs.
    """
    if max_days is None:
        max_days = scan_horizon_days()
    with open("polymarket_data.json", "r", encoding="utf-8") as file:
        data = json.load(file)

    candidates, token_ids = _collect_market_candidates(
        data,
        max_days,
        max_days,
    )
    price_lookup = fetch_buy_prices(token_ids)

    clean_markets_polymarket.clear()
    for candidate in candidates:
        market = candidate["market"]
        event_tags = candidate["event_tags"]
        prices = prices_from_tokens(
            candidate["yes_token_id"],
            candidate["no_token_id"],
            price_lookup,
        )
        if prices is None:
            continue

        yes_price, no_price = prices
        if not is_tradable_binary_book(yes_price, no_price):
            continue

        fee_rate = polymarket_fee_rate_from_market(market, event_tags)
        activity = polymarket_activity_from_gamma(market)
        clean_markets_polymarket.append({
            "market_question": candidate["market_question"],
            "yes_price": yes_price,
            "no_price": no_price,
            "fee_rate": fee_rate,
            "fees_enabled": bool(market.get("feesEnabled")),
            "end_date": candidate["end_date"],
            "days_to_resolution": round(days_until_resolution(candidate["end_date"]), 2),
            "tags": [tag.get("slug", "") for tag in event_tags if tag.get("slug")],
            "group_item_title": market.get("groupItemTitle") or "",
            "event_matchup": candidate.get("event_matchup"),
            "event_title": candidate.get("event_title", ""),
            "event_id": candidate.get("event_id"),
            "description": (
                market.get("description")
                or candidate.get("event_description")
                or ""
            ),
            "resolution_source": (
                market.get("resolutionSource")
                or candidate.get("event_resolution_source")
                or ""
            ),
            "rules_primary": market.get("rulesPrimary") or market.get("rules") or "",
            "yes_token_id": candidate["yes_token_id"],
            "no_token_id": candidate["no_token_id"],
            "condition_id": market.get("conditionId"),
            "price_source": "clob_best_ask",
            "volume": activity.get("volume"),
            "volume_24h": activity.get("volume_24h"),
            "liquidity": activity.get("liquidity"),
            "open_interest": activity.get("open_interest"),
        })

    print(f"Total clean markets: {len(clean_markets_polymarket)}")
    return clean_markets_polymarket


def refresh_polymarket_ask_prices(markets):
    """Reprice existing Polymarket markets from the CLOB (used by the logger)."""
    token_ids = []
    for market in markets:
        yes_token_id = market.get("yes_token_id")
        no_token_id = market.get("no_token_id")
        if yes_token_id and no_token_id:
            token_ids.extend([yes_token_id, no_token_id])

    if not token_ids:
        return 0

    price_lookup = fetch_buy_prices(token_ids)
    updated = 0
    for market in markets:
        prices = prices_from_tokens(
            market.get("yes_token_id"),
            market.get("no_token_id"),
            price_lookup,
        )
        if prices is None:
            continue

        market["yes_price"], market["no_price"] = prices
        market["price_source"] = "clob_best_ask"
        updated += 1

    return updated
