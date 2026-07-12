# Order-book depth, fill sizing, and market activity for arb verification.
import time

import requests

from config import ENRICH_LIQUIDITY_ON_SCAN, POLYMARKET_CLOB_BOOK_BATCH_SIZE

POLYMARKET_BOOK_URL = "https://clob.polymarket.com/book"
POLYMARKET_BOOKS_URL = "https://clob.polymarket.com/books"

_book_cache = {}


def parse_fp(value):
    """Parse Kalshi fixed-point string fields (e.g. volume_fp, yes_ask_size_fp)."""
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def kalshi_top_of_book_sizes(raw_market):
    """Top-of-book contract sizes from a raw Kalshi market payload."""
    return {
        "yes_ask_size": parse_fp(raw_market.get("yes_ask_size_fp")),
        "no_ask_size": parse_fp(raw_market.get("no_ask_size_fp")),
    }


def kalshi_activity(raw_market):
    """Volume and open interest from a raw Kalshi market payload."""
    return {
        "volume": parse_fp(raw_market.get("volume_fp")),
        "volume_24h": parse_fp(raw_market.get("volume_24h_fp")),
        "open_interest": parse_fp(raw_market.get("open_interest_fp")),
    }


def polymarket_activity_from_gamma(market):
    """Best-effort activity fields from Gamma market metadata."""
    volume = market.get("volumeNum")
    if volume is None:
        volume = market.get("volume")
    liquidity = market.get("liquidityClob")
    if liquidity is None:
        liquidity = market.get("liquidityNum")
    if liquidity is None:
        liquidity = market.get("liquidity")
    open_interest = market.get("openInterest")
    return {
        "volume": _safe_float(volume),
        "volume_24h": _safe_float(market.get("volume24hr") or market.get("volume24hrClob")),
        "liquidity": _safe_float(liquidity),
        "open_interest": _safe_float(open_interest),
    }


def _safe_float(value):
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def size_at_or_better_asks(book_asks, max_price):
    """Sum ask sizes where price is at or better (<=) than max_price."""
    if not book_asks or max_price is None:
        return None

    total = 0.0
    found = False
    for level in book_asks:
        try:
            price = float(level.get("price"))
            size = float(level.get("size"))
        except (TypeError, ValueError, AttributeError):
            continue
        if price <= float(max_price) + 1e-9:
            total += size
            found = True

    return total if found else 0.0


def fetch_polymarket_book(token_id):
    """Fetch a single Polymarket CLOB order book (cached per scan)."""
    token_id = str(token_id)
    if token_id in _book_cache:
        return _book_cache[token_id]

    response = requests.get(
        POLYMARKET_BOOK_URL,
        params={"token_id": token_id},
        timeout=30,
    )
    response.raise_for_status()
    book = response.json()
    _book_cache[token_id] = book
    return book


def fetch_polymarket_books(token_ids):
    """Batch-fetch Polymarket order books."""
    unique_ids = []
    seen = set()
    for token_id in token_ids:
        token_id = str(token_id)
        if not token_id or token_id in seen:
            continue
        seen.add(token_id)
        unique_ids.append(token_id)

    for start in range(0, len(unique_ids), POLYMARKET_CLOB_BOOK_BATCH_SIZE):
        batch = unique_ids[start:start + POLYMARKET_CLOB_BOOK_BATCH_SIZE]
        missing = [token_id for token_id in batch if token_id not in _book_cache]
        if not missing:
            continue

        response = requests.post(
            POLYMARKET_BOOKS_URL,
            json=[{"token_id": token_id} for token_id in missing],
            timeout=60,
        )
        response.raise_for_status()
        books = response.json()
        if isinstance(books, list):
            for book in books:
                asset_id = str(book.get("asset_id") or book.get("token_id") or "")
                if asset_id:
                    _book_cache[asset_id] = book
        time.sleep(0.05)

    return {token_id: _book_cache.get(token_id) for token_id in unique_ids}


def clear_book_cache():
    """Reset per-scan book cache."""
    _book_cache.clear()


def _token_id_for_side(market, side):
    side_key = str(side).upper()
    if side_key == "YES":
        return market.get("yes_token_id")
    if side_key == "NO":
        return market.get("no_token_id")
    return None


def _top_of_book_size(market, side):
    side_key = str(side).upper()
    if side_key == "YES":
        return market.get("yes_ask_size")
    if side_key == "NO":
        return market.get("no_ask_size")
    return None


def leg_fillable_size(market, side, max_price, book=None):
    """
    Contracts available at or better than max_price for one leg.

    Kalshi: top-of-book size when price matches best ask.
    Polymarket: walk CLOB ask ladder when book is provided.
    ForecastEx: unknown depth.
    """
    platform = (market.get("platform") or "").lower()
    side_key = str(side).upper()

    if platform == "forecastex":
        return None

    if platform == "kalshi":
        top_size = _top_of_book_size(market, side_key)
        if top_size is None:
            return None
        leg_price = market.get("yes_price") if side_key == "YES" else market.get("no_price")
        if leg_price is not None and abs(float(leg_price) - float(max_price)) < 1e-6:
            return top_size
        return top_size

    if platform == "polymarket":
        token_id = _token_id_for_side(market, side_key)
        if not token_id:
            return None
        if book is None:
            book = fetch_polymarket_book(token_id)
        asks = book.get("asks") or []
        return size_at_or_better_asks(asks, max_price)

    return None


def _market_for_leg(opportunity, leg):
    """Resolve normalized market dict for a buy_plan leg."""
    platform = leg.get("platform")
    market_a = opportunity.get("market_a") or {}
    market_b = opportunity.get("market_b") or {}
    if market_a.get("platform") == platform:
        return market_a
    if market_b.get("platform") == platform:
        return market_b
    if opportunity.get("platform_a") == platform:
        return market_a
    if opportunity.get("platform_b") == platform:
        return market_b
    return market_a


def enrich_opportunity_liquidity(opportunity, poly_books=None):
    """Attach fillable size and activity metrics to one opportunity."""
    buy_plan = opportunity.get("buy_plan") or {}
    legs = buy_plan.get("legs") or []
    if not legs:
        return opportunity

    poly_books = poly_books or {}
    leg_details = []
    fill_sizes = []

    for leg in legs:
        market = _market_for_leg(opportunity, leg)
        platform = (leg.get("platform") or market.get("platform") or "").lower()
        side = leg.get("side")
        price = leg.get("price")

        book = None
        if platform == "polymarket":
            token_id = _token_id_for_side(market, side)
            if token_id:
                book = poly_books.get(str(token_id))
                if book is None:
                    book = fetch_polymarket_book(token_id)

        size_at_price = leg_fillable_size(market, side, price, book=book)
        if size_at_price is not None:
            fill_sizes.append(size_at_price)

        leg_detail = {
            "platform": leg.get("platform"),
            "side": side,
            "price": price,
            "size_at_price": size_at_price,
            "volume_24h": market.get("volume_24h"),
            "volume": market.get("volume"),
            "open_interest": market.get("open_interest"),
            "liquidity": market.get("liquidity"),
        }
        if size_at_price is None and platform == "forecastex":
            leg_detail["size_at_price"] = None
            leg_detail["size_note"] = "unknown"

        leg["size_at_price"] = size_at_price
        if market.get("volume_24h") is not None:
            leg["volume_24h"] = market.get("volume_24h")

        leg_details.append(leg_detail)

    max_fillable = None
    if fill_sizes and len(fill_sizes) == len(legs):
        max_fillable = min(fill_sizes)
    profit_per_contract = opportunity.get("profit", 0.0)
    total_cost_per_contract = opportunity.get("total_cost", 0.0)

    volumes_24h = [leg.get("volume_24h") for leg in leg_details if leg.get("volume_24h") is not None]
    open_interests = [leg.get("open_interest") for leg in leg_details if leg.get("open_interest") is not None]

    liquidity = {
        "max_fillable_contracts": round(max_fillable, 2) if max_fillable is not None else None,
        "max_profit_usd": round(profit_per_contract * max_fillable, 4) if max_fillable is not None else None,
        "max_capital_usd": round(total_cost_per_contract * max_fillable, 4) if max_fillable is not None else None,
        "legs": leg_details,
        "activity": {
            "min_volume_24h": min(volumes_24h) if volumes_24h else None,
            "min_open_interest": min(open_interests) if open_interests else None,
        },
    }
    opportunity["liquidity"] = liquidity
    return opportunity


def enrich_opportunities_liquidity(opportunities):
    """Enrich all opportunities with depth and activity (Polymarket books batched)."""
    if not ENRICH_LIQUIDITY_ON_SCAN:
        return opportunities

    clear_book_cache()

    token_ids = []
    for opportunity in opportunities:
        for leg in (opportunity.get("buy_plan") or {}).get("legs") or []:
            market = _market_for_leg(opportunity, leg)
            if (market.get("platform") or "").lower() != "polymarket":
                continue
            token_id = _token_id_for_side(market, leg.get("side"))
            if token_id:
                token_ids.append(str(token_id))

    poly_books = fetch_polymarket_books(token_ids) if token_ids else {}

    enriched = []
    for opportunity in opportunities:
        enriched.append(enrich_opportunity_liquidity(opportunity, poly_books=poly_books))
    return enriched


def max_arb_fillable(opportunity):
    """Return liquidity summary dict for an opportunity."""
    liquidity = opportunity.get("liquidity")
    if liquidity:
        return liquidity
    return enrich_opportunity_liquidity(opportunity).get("liquidity", {})
