# Fetches raw Kalshi market data and converts it into a normalized market list.
import json
import time
from pathlib import Path

import requests

from config import (
    KALSHI_MAX_MARKETS,
    KALSHI_PAGE_DELAY_SECONDS,
    KALSHI_PAGE_LIMIT,
    KALSHI_POLITICS_SERIES_DELAY_SECONDS,
    KALSHI_PRIORITY_SERIES,
    KALSHI_REQUEST_MAX_RETRIES,
    KALSHI_SERIES_DELAY_SECONDS,
    KALSHI_USE_CACHED_ON_RATE_LIMIT,
    scan_horizon_days,
)
from politics_normalization import US_STATE_CODES
from fees import kalshi_fee_multiplier
from market_utils import days_until_resolution, horizon_end_timestamp, is_tradable_binary_book, parse_iso_datetime, utc_timestamp
from market_liquidity import kalshi_activity, kalshi_top_of_book_sizes

MARKETS_URL = "https://external-api.kalshi.com/trade-api/v2/markets"

# Shared list used by other modules after extract_kalshi_details() runs.
clean_markets_kalshi = []
last_kalshi_funnel = {}


class KalshiRateLimitError(requests.HTTPError):
    """Kalshi API rate limit exceeded after retries."""


def _kalshi_retry_delay(response, attempt):
    """Seconds to wait before retrying a throttled Kalshi request."""
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass
    return min(2.0 * (2 ** attempt), 60.0)


def kalshi_get(params, context="markets"):
    """
    GET Kalshi /markets with retry/backoff on 429 and transient 5xx errors.
    """
    last_response = None
    for attempt in range(KALSHI_REQUEST_MAX_RETRIES):
        response = requests.get(MARKETS_URL, params=params, timeout=60)
        last_response = response

        if response.status_code == 429:
            delay = _kalshi_retry_delay(response, attempt)
            print(
                f"  Kalshi rate limit ({context}), "
                f"retry {attempt + 1}/{KALSHI_REQUEST_MAX_RETRIES} in {delay:.1f}s"
            )
            time.sleep(delay)
            continue

        if response.status_code in (500, 502, 503, 504):
            delay = _kalshi_retry_delay(response, attempt)
            print(
                f"  Kalshi server error {response.status_code} ({context}), "
                f"retry {attempt + 1}/{KALSHI_REQUEST_MAX_RETRIES} in {delay:.1f}s"
            )
            time.sleep(delay)
            continue

        if response.status_code == 404:
            return response

        response.raise_for_status()
        return response

    if last_response is not None and last_response.status_code == 429:
        raise KalshiRateLimitError(
            f"Kalshi rate limit exceeded for {context} after {KALSHI_REQUEST_MAX_RETRIES} retries",
            response=last_response,
        )
    if last_response is not None:
        last_response.raise_for_status()
    raise requests.RequestException(f"Kalshi request failed for {context}")


def _kalshi_cache_path():
    return "kalshi_data.json"


def kalshi_cache_available():
    """True when a prior Kalshi payload exists on disk."""
    return Path(_kalshi_cache_path()).exists()


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

        response = kalshi_get(params, context="bulk markets")
        page_data = response.json()
        if "error" in page_data:
            raise ValueError(f"Kalshi API error: {page_data['error']}")

        markets = page_data.get("markets", [])
        all_markets.extend(markets)

        next_cursor = page_data.get("cursor")
        if not next_cursor or not markets:
            break
        cursor = next_cursor
        time.sleep(KALSHI_PAGE_DELAY_SECONDS)

    kalshi_payload = {
        "fetch_mode": "short_term_markets",
        "max_days_to_resolution": max_days,
        "fetched_at": now_ts,
        "markets": all_markets[:KALSHI_MAX_MARKETS],
        "cursor": cursor,
    }
    with open(_kalshi_cache_path(), "w", encoding="utf-8") as file:
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

    with open(_kalshi_cache_path(), "r", encoding="utf-8") as file:
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

            try:
                response = kalshi_get(params, context=f"series {series_ticker}")
            except KalshiRateLimitError:
                print(f"  Kalshi rate limit: skipping remaining priority series after {series_ticker}")
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
            time.sleep(KALSHI_SERIES_DELAY_SECONDS)

        time.sleep(KALSHI_SERIES_DELAY_SECONDS)

    payload["markets"] = existing
    payload["priority_series_added"] = added
    with open(_kalshi_cache_path(), "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    print(f"Kalshi priority series supplement added {added} markets")
    return added


def fetch_politics_state_series():
    """
    Fetch per-state Senate/House series (SENATEID, SENATEIA, ...).

    Bulk pagination often misses these; each state is a separate Kalshi series.
    """
    with open(_kalshi_cache_path(), "r", encoding="utf-8") as file:
        payload = json.load(file)

    existing = payload.get("markets", [])
    seen_tickers = {market.get("ticker") for market in existing}
    added = 0
    rate_limited = False

    prefixes = [f"SENATE{code.upper()}" for code in US_STATE_CODES]
    prefixes += [f"HOUSE{code.upper()}" for code in US_STATE_CODES]

    for series_ticker in prefixes:
        if rate_limited:
            break

        cursor = None
        while True:
            params = {"status": "open", "limit": KALSHI_PAGE_LIMIT, "series_ticker": series_ticker}
            if cursor:
                params["cursor"] = cursor

            try:
                response = kalshi_get(params, context=f"politics {series_ticker}")
            except KalshiRateLimitError:
                print("  Kalshi rate limit: stopping politics state series supplement")
                rate_limited = True
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
            time.sleep(KALSHI_POLITICS_SERIES_DELAY_SECONDS)

        time.sleep(KALSHI_POLITICS_SERIES_DELAY_SECONDS)

    payload["markets"] = existing
    payload["politics_series_added"] = added
    payload["politics_rate_limited"] = rate_limited
    with open(_kalshi_cache_path(), "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    print(f"Kalshi politics state series added {added} markets")
    return added


def fetch_kalshi_data_with_priorities(max_days=None):
    """Fetch bulk markets plus priority and politics series."""
    try:
        fetch_kalshi_data(max_days=max_days)
        fetch_priority_series(max_days=max_days)
        fetch_politics_state_series()
    except KalshiRateLimitError as exc:
        if KALSHI_USE_CACHED_ON_RATE_LIMIT and kalshi_cache_available():
            print(f"Kalshi fetch rate limited; using cached {_kalshi_cache_path()}: {exc}")
            return
        raise


def get_raw_kalshi_markets():
    """Return raw Kalshi market dicts from the saved JSON payload."""
    with open(_kalshi_cache_path(), "r", encoding="utf-8") as file:
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
    global last_kalshi_funnel

    if max_days is None:
        max_days = scan_horizon_days()
    if macro_days is None:
        macro_days = max_days
    with open(_kalshi_cache_path(), "r", encoding="utf-8") as file:
        kalshi_data = json.load(file)

    clean_markets_kalshi.clear()
    now = utc_timestamp()
    max_close_ts = horizon_end_timestamp(macro_days)

    funnel = {
        "raw_fetched": 0,
        "dropped_mve": 0,
        "dropped_horizon": 0,
        "dropped_no_prices": 0,
        "dropped_book_quality": 0,
        "clean_extracted": 0,
        "extract_horizon_days": macro_days,
    }

    for market in _iter_kalshi_markets(kalshi_data):
        funnel["raw_fetched"] += 1

        if market.get("mve_selected_legs"):
            funnel["dropped_mve"] += 1
            continue

        close_time = _market_close_time(market)
        close_dt = parse_iso_datetime(close_time)
        if close_dt is not None and not _is_long_dated_politics_market(market):
            close_ts = int(close_dt.timestamp())
            if close_ts < now or close_ts > max_close_ts:
                funnel["dropped_horizon"] += 1
                continue

        market_question = market.get("title")
        yes_price = market.get("yes_ask_dollars")
        no_price = market.get("no_ask_dollars")
        if yes_price is None or no_price is None:
            funnel["dropped_no_prices"] += 1
            continue

        price_list = [float(yes_price), float(no_price)]
        if not is_tradable_binary_book(price_list[0], price_list[1]):
            funnel["dropped_book_quality"] += 1
            continue

        ticker = market.get("ticker")
        sizes = kalshi_top_of_book_sizes(market)
        activity = kalshi_activity(market)
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
            "yes_ask_size": sizes.get("yes_ask_size"),
            "no_ask_size": sizes.get("no_ask_size"),
            "volume": activity.get("volume"),
            "volume_24h": activity.get("volume_24h"),
            "open_interest": activity.get("open_interest"),
        })
        funnel["clean_extracted"] += 1

    last_kalshi_funnel = funnel
    print(f"Total clean markets for Kalshi: {len(clean_markets_kalshi)}")
    print(
        "Kalshi extract funnel: "
        f"raw={funnel['raw_fetched']} "
        f"horizon={funnel['dropped_horizon']} "
        f"no_prices={funnel['dropped_no_prices']} "
        f"book={funnel['dropped_book_quality']} "
        f"clean={funnel['clean_extracted']}"
    )
    return clean_markets_kalshi
