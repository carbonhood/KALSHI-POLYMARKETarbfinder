# ForecastEx market data (Interactive Brokers event contracts).
#
# Live fetch requires IBKR Client Portal Gateway:
#   https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
#
# Set IBKR_GATEWAY_URL=http://localhost:5000/v1/api in .env when gateway is running.
# Without gateway, place a manual export at forecastex_data.json (see .env.example).

import json
import os
from pathlib import Path

import requests

from fees import FORECASTEX_SPREAD_PREMIUM
from market_utils import days_until_resolution, is_tradable_binary_book, parse_iso_datetime

FORECASTEX_CACHE = Path("forecastex_data.json")
clean_markets_forecastex = []


def _load_env(key):
    value = os.environ.get(key, "").strip()
    if value:
        return value
    env_path = Path(".env")
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, val = line.split("=", 1)
        if name.strip() == key:
            return val.strip().strip('"').strip("'")
    return ""


def get_ibkr_gateway_url():
    return _load_env("IBKR_GATEWAY_URL") or "http://localhost:5000/v1/api"


def load_cached_forecastex():
    if not FORECASTEX_CACHE.exists():
        return {"markets": [], "source": "empty"}
    with open(FORECASTEX_CACHE, "r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_raw_market(raw):
    """Convert ForecastEx/IBKR raw dict to pipeline market format."""
    title = raw.get("market_question") or raw.get("title") or raw.get("description")
    yes_price = raw.get("yes_price")
    no_price = raw.get("no_price")

    if yes_price is None and raw.get("yes_ask") is not None:
        yes_price = float(raw["yes_ask"])
    if no_price is None and raw.get("no_ask") is not None:
        no_price = float(raw["no_ask"])

    if yes_price is None or no_price is None:
        return None

    yes_price = float(yes_price)
    no_price = float(no_price)

    end_date = raw.get("end_date") or raw.get("expiration") or raw.get("lastTradeDate")
    close_time = raw.get("close_time") or end_date

    return {
        "platform": "ForecastEx",
        "market_question": title,
        "yes_price": yes_price,
        "no_price": no_price,
        "end_date": end_date,
        "close_time": close_time,
        "days_to_resolution": round(days_until_resolution(end_date or close_time) or 0, 2),
        "conid": raw.get("conid"),
        "event_title": raw.get("event_title", ""),
        "rules_primary": raw.get("rules_primary", ""),
        "spread_premium": FORECASTEX_SPREAD_PREMIUM,
        "price_source": raw.get("price_source", "cache"),
    }


def fetch_from_ibkr_gateway(gateway_url=None, search_symbols=None):
    """
    Best-effort pull from local IBKR Client Portal Gateway.

    Requires authenticated gateway session. Returns list of normalized markets.
    """
    base = (gateway_url or get_ibkr_gateway_url()).rstrip("/")
    symbols = search_symbols or ("FF", "CPI", "UNRATE", "GDP")
    markets = []

    try:
        requests.get(f"{base}/tickle", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        raise ConnectionError(
            f"IBKR gateway not reachable at {base}: {exc}. "
            "Start Client Portal Gateway or use forecastex_data.json cache."
        ) from exc

    for symbol in symbols:
        try:
            response = requests.get(
                f"{base}/iserver/secdef/search",
                params={"symbol": symbol, "exchange": "FORECASTX", "sectype": "OPT"},
                timeout=30,
            )
            response.raise_for_status()
            results = response.json()
        except requests.RequestException:
            continue

        if not isinstance(results, list):
            continue

        for item in results[:20]:
            conid = item.get("conid")
            if not conid:
                continue
            try:
                snap = requests.get(
                    f"{base}/iserver/marketdata/snapshot",
                    params={"conids": conid, "fields": "31,84,86"},
                    timeout=30,
                )
                snap.raise_for_status()
                quotes = snap.json()
            except requests.RequestException:
                continue

            if not quotes:
                continue
            quote = quotes[0] if isinstance(quotes, list) else quotes
            yes_ask = quote.get("86") or quote.get("ask")
            if yes_ask is None:
                continue
            try:
                yes_price = float(yes_ask)
            except (TypeError, ValueError):
                continue
            no_price = max(0.01, round(1.0 - yes_price + FORECASTEX_SPREAD_PREMIUM / 2, 4))

            normalized = _normalize_raw_market({
                "market_question": item.get("description") or item.get("companyName") or symbol,
                "yes_price": yes_price,
                "no_price": no_price,
                "conid": conid,
                "price_source": "ibkr_gateway",
            })
            if normalized and is_tradable_binary_book(normalized["yes_price"], normalized["no_price"]):
                markets.append(normalized)

    payload = {
        "source": "ibkr_gateway",
        "gateway_url": base,
        "markets": markets,
    }
    with open(FORECASTEX_CACHE, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    print(f"ForecastEx: saved {len(markets)} markets from IBKR gateway")
    return payload


def extract_forecastex_details(use_gateway=False):
    """Load ForecastEx markets from gateway or cache into clean_markets_forecastex."""
    clean_markets_forecastex.clear()

    if use_gateway:
        try:
            payload = fetch_from_ibkr_gateway()
        except ConnectionError as exc:
            print(f"ForecastEx gateway fetch skipped: {exc}")
            payload = load_cached_forecastex()
    else:
        payload = load_cached_forecastex()

    for raw in payload.get("markets", []):
        market = _normalize_raw_market(raw)
        if not market:
            continue
        if not is_tradable_binary_book(market["yes_price"], market["no_price"]):
            continue
        clean_markets_forecastex.append(market)

    print(f"Total clean ForecastEx markets: {len(clean_markets_forecastex)}")
    return clean_markets_forecastex
