# Fetches raw Kalshi market data and converts it into a normalized market list.
import json
import time

import requests

from config import KALSHI_MAX_MARKETS, KALSHI_PAGE_LIMIT, KALSHI_PRIORITY_SERIES, scan_horizon_days
from politics_normalization import US_STATE_CODES
from fees import kalshi_fee_multiplier
from market_utils import days_until_resolution, horizon_end_timestamp, is_tradable_binary_book, parse_iso_datetime, utc_timestamp

MARKETS_URL = "https://external-api.kalshi.com/trade-api/v2/markets"

# Shared list used by other modules after extract_kalshi_details() runs.
clean_markets_kalshi = []


def fetch_kalshi_data(max_days=None):
    """
    Download open Kalshi markets closing within max_days.

    Uses the /markets endpoint with close-time filters so we get sports and
    other near-term markets instead of long-dated election events.
    """
    if max_days is None:
        max_days = scan_horizon_days()

    all_markets = []
    cursor = None
    now_ts = utc_timestamp()
    max_close_ts = horizon_end_timestamp(max_days)

    while len(all_markets) < KALSHI_MAX_MARKETS:
        params = {
            "status": "open",
            "limit": KALSHI_PAGE_LIMIT,
            "min_close_ts": now_ts,
            "max_close_ts": max_close_ts,
            "mve_filter": "exclude",
        }
        if cursor:
            params["cursor"] = cursor

        response = requests.get(MARKETS_URL, params=params, timeout=60)
        response.raise_for_status()
        page_data = response.json()
        if "error" in page_data:
            raise ValueError(f"Kalshi API error: {page_data['error']}")

        markets = page_data.get("markets", [])
        all_markets.extend(markets)

        next_cursor = page_data.get("cursor")
        if not next_cursor or not markets:
            break
        cursor = next_cursor
        time.sleep(0.05)

    kalshi_payload = {
        "fetch_mode": "short_term_markets",
        "max_days_to_resolution": max_days,
        "fetched_at": now_ts,
        "markets": all_markets[:KALSHI_MAX_MARKETS],
        "cursor": cursor,
    }
    with open("kalshi_data.json", "w", encoding="utf-8") as file:
        json.dump(kalshi_payload, file, indent=4)
    print(
        f"Kalshi data saved to kalshi_data.json "
        f"({len(kalshi_payload['markets'])} markets within {max_days} days)"
    )
    return kalshi_payload


def fetch_priority_series(max_days=None):
    """
    Fetch Kalshi markets from high-overlap series and merge into kalshi_data.json.

    Bulk time-filtered pagination can miss COD, golf, and other series that sit
    beyond the first N pages.
    """
    if max_days is None:
        max_days = scan_horizon_days()

    with open("kalshi_data.json", "r", encoding="utf-8") as file:
        payload = json.load(file)

    existing = payload.get("markets", [])
    seen_tickers = {market.get("ticker") for market in existing}
    added = 0

    for series_ticker in KALSHI_PRIORITY_SERIES:
        cursor = None
        while True:
            params = {
                "status": "open",
                "limit": KALSHI_PAGE_LIMIT,
                "series_ticker": series_ticker,
            }
            if cursor:
                params["cursor"] = cursor

            for attempt in range(4):
                response = requests.get(MARKETS_URL, params=params, timeout=60)
                if response.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                break
            else:
                print(f"  Kalshi rate limit: skipping series {series_ticker}")
                break

            page_data = response.json()
            markets = page_data.get("markets", [])

            for market in markets:
                ticker = market.get("ticker")
                if ticker in seen_tickers:
                    continue
                seen_tickers.add(ticker)
                existing.append(market)
                added += 1

            cursor = page_data.get("cursor")
            if not cursor or not markets:
                break
            time.sleep(0.05)

    payload["markets"] = existing
    payload["priority_series_added"] = added
    with open("kalshi_data.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    print(f"Kalshi priority series supplement added {added} markets")
    return added


def fetch_politics_state_series():
    """
    Fetch per-state Senate/House series (SENATEID, SENATEIA, ...).

    Bulk pagination often misses these; each state is a separate Kalshi series.
    """
    with open("kalshi_data.json", "r", encoding="utf-8") as file:
        payload = json.load(file)

    existing = payload.get("markets", [])
    seen_tickers = {market.get("ticker") for market in existing}
    added = 0

    prefixes = [f"SENATE{code.upper()}" for code in US_STATE_CODES]
    prefixes += [f"HOUSE{code.upper()}" for code in US_STATE_CODES]

    for series_ticker in prefixes:
        cursor = None
        while True:
            params = {"status": "open", "limit": KALSHI_PAGE_LIMIT, "series_ticker": series_ticker}
            if cursor:
                params["cursor"] = cursor

            for attempt in range(4):
                response = requests.get(MARKETS_URL, params=params, timeout=60)
                if response.status_code == 429:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if response.status_code == 404:
                    break
                response.raise_for_status()
                break
            else:
                break

            if response.status_code == 404:
                break

            page_data = response.json()
            markets = page_data.get("markets", [])
            for market in markets:
                ticker = market.get("ticker")
                if ticker in seen_tickers:
                    continue
                seen_tickers.add(ticker)
                existing.append(market)
                added += 1

            cursor = page_data.get("cursor")
            if not cursor or not markets:
                break
            time.sleep(0.15)

    payload["markets"] = existing
    payload["politics_series_added"] = added
    with open("kalshi_data.json", "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    print(f"Kalshi politics state series added {added} markets")
    return added


def fetch_kalshi_data_with_priorities(max_days=None):
    """Fetch bulk markets plus priority and politics series."""
    fetch_kalshi_data(max_days=max_days)
    fetch_priority_series(max_days=max_days)
    fetch_politics_state_series()


def get_raw_kalshi_markets():
    """Return raw Kalshi market dicts from the saved JSON payload."""
    with open("kalshi_data.json", "r", encoding="utf-8") as file:
        kalshi_data = json.load(file)
    return list(_iter_kalshi_markets(kalshi_data))


def _iter_kalshi_markets(kalshi_data):
    """Yield raw market dicts from either short-term or legacy event payloads."""
    if "markets" in kalshi_data:
        yield from kalshi_data["markets"]
        return

    if "events" not in kalshi_data:
        raise ValueError(
            "kalshi_data.json has no markets or events. Re-run fetch_kalshi_data()."
        )

    for event in kalshi_data["events"]:
        for market in event.get("markets", []):
            yield market


def _is_long_dated_politics_market(market):
    """Kalshi Senate/House markets often have far-future API close times."""
    ticker = (market.get("ticker") or market.get("event_ticker") or "").upper()
    title = (market.get("title") or market.get("market_question") or "").lower()
    if ticker.startswith(("SENATE", "HOUSE", "GOV")):
        return True
    if "senate race" in title or "house race" in title:
        return True
    if "control of the senate" in title or "control of the house" in title:
        return True
    return False


def _market_close_time(market):
    return (
        market.get("close_time")
        or market.get("expected_expiration_time")
        or market.get("expiration_time")
    )


def extract_kalshi_details(max_days=None, macro_days=None):
    """
    Read kalshi_data.json and build clean_markets_kalshi with only markets
    that have usable yes/no ask prices and resolve within the scan horizon.
    """
    if max_days is None:
        max_days = scan_horizon_days()
    if macro_days is None:
        macro_days = max_days
    with open("kalshi_data.json", "r", encoding="utf-8") as file:
        kalshi_data = json.load(file)

    clean_markets_kalshi.clear()
    now = utc_timestamp()
    max_close_ts = horizon_end_timestamp(macro_days)

    for market in _iter_kalshi_markets(kalshi_data):
        if market.get("mve_selected_legs"):
            continue

        close_time = _market_close_time(market)
        close_dt = parse_iso_datetime(close_time)
        if close_dt is not None and not _is_long_dated_politics_market(market):
            close_ts = int(close_dt.timestamp())
            if close_ts < now or close_ts > max_close_ts:
                continue

        market_question = market.get("title")
        yes_price = market.get("yes_ask_dollars")
        no_price = market.get("no_ask_dollars")
        if yes_price is None or no_price is None:
            continue

        price_list = [float(yes_price), float(no_price)]
        if is_tradable_binary_book(price_list[0], price_list[1]):
            ticker = market.get("ticker")
            clean_markets_kalshi.append({
                "market_question": market_question,
                "yes_price": price_list[0],
                "no_price": price_list[1],
                "ticker": ticker,
                "event_ticker": market.get("event_ticker"),
                "close_time": close_time,
                "end_date": close_time,
                "days_to_resolution": round(days_until_resolution(close_time) or 0, 2),
                "yes_sub_title": market.get("yes_sub_title") or "",
                "no_sub_title": market.get("no_sub_title") or "",
                "occurrence_datetime": market.get("occurrence_datetime"),
                "rules_primary": market.get("rules_primary") or "",
                "fee_multiplier": kalshi_fee_multiplier(ticker),
                "platform": "Kalshi",
            })

    print(f"Total clean markets for Kalshi: {len(clean_markets_kalshi)}")
    return clean_markets_kalshi
