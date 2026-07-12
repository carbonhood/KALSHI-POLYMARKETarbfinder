# Fee calculations for Kalshi and Polymarket.
#
# We use taker fees because arbitrage usually means taking existing ask prices.
# Sources:
# - Kalshi fee schedule: round up(0.07 x C x P x (1-P)) for standard markets
# - Polymarket docs: fee = C x feeRate x p x (1-p)

import math

# Standard Kalshi taker multiplier for most prediction markets.
KALSHI_STANDARD_TAKER_RATE = 0.07

# Reduced Kalshi taker multiplier for select index markets.
KALSHI_INDEX_TAKER_RATE = 0.035

# Fallback Polymarket taker rates by category when API fee data is missing.
POLYMARKET_CATEGORY_FEE_RATES = {
    "crypto": 0.07,
    "sports": 0.05,
    "finance": 0.04,
    "politics": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "tech": 0.04,
    "mentions": 0.04,
    "geopolitics": 0.0,
}


def kalshi_fee_multiplier(ticker=None):
    """Return the Kalshi taker fee multiplier for a market ticker."""
    if not ticker:
        return KALSHI_STANDARD_TAKER_RATE

    upper_ticker = ticker.upper()
    if upper_ticker.startswith("INX") or upper_ticker.startswith("NASDAQ100"):
        return KALSHI_INDEX_TAKER_RATE

    return KALSHI_STANDARD_TAKER_RATE


def kalshi_taker_fee(price, contracts=1, fee_multiplier=KALSHI_STANDARD_TAKER_RATE):
    """
    Calculate Kalshi taker fee for one side of a trade.

    Kalshi rounds up to the next cent.
    """
    raw_fee = fee_multiplier * contracts * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


def polymarket_taker_fee(price, fee_rate, contracts=1):
    """
    Calculate Polymarket taker fee for one side of a trade.

    Polymarket rounds to 5 decimal places. Very small fees become zero.
    """
    if not fee_rate:
        return 0.0

    raw_fee = contracts * fee_rate * price * (1 - price)
    fee = round(raw_fee, 5)
    if fee < 0.00001:
        return 0.0

    return fee


def polymarket_fee_rate_from_market(market, event_tags=None):
    """
    Read Polymarket fee settings from market data when available.

    Prefer the API's feeSchedule.rate. Fall back to event tags, then zero.
    """
    if not market.get("feesEnabled"):
        return 0.0

    fee_schedule = market.get("feeSchedule") or {}
    if fee_schedule.get("rate") is not None:
        return float(fee_schedule["rate"])

    if event_tags:
        for tag in event_tags:
            label = str(tag.get("label", tag.get("slug", ""))).lower()
            if label in POLYMARKET_CATEGORY_FEE_RATES:
                return POLYMARKET_CATEGORY_FEE_RATES[label]

    return POLYMARKET_CATEGORY_FEE_RATES["politics"]


def build_internal_buy_plan(platform, yes_price, no_price, yes_fee, no_fee):
    """Return the exact YES/NO legs to buy for same-platform arbitrage."""
    return {
        "type": "internal",
        "summary": f"Buy YES and NO on {platform}",
        "legs": [
            {
                "platform": platform,
                "side": "YES",
                "price": yes_price,
                "fee": yes_fee,
                "total": round(yes_price + yes_fee, 5),
            },
            {
                "platform": platform,
                "side": "NO",
                "price": no_price,
                "fee": no_fee,
                "total": round(no_price + no_fee, 5),
            },
        ],
    }


def build_cross_platform_buy_plan(strategy_key, poly_market, kalshi_market, strategy):
    """Return the exact cross-platform YES/NO legs to buy."""
    if strategy_key == "buy_yes_polymarket_buy_no_kalshi":
        legs = [
            {
                "platform": "Polymarket",
                "side": "YES",
                "market": poly_market["market_question"],
                "price": poly_market["yes_price"],
                "fee": strategy["yes_fee"],
                "total": round(poly_market["yes_price"] + strategy["yes_fee"], 5),
            },
            {
                "platform": "Kalshi",
                "side": "NO",
                "market": kalshi_market["market_question"],
                "price": kalshi_market["no_price"],
                "fee": strategy["no_fee"],
                "total": round(kalshi_market["no_price"] + strategy["no_fee"], 5),
            },
        ]
        summary = "Buy YES on Polymarket and NO on Kalshi"
    else:
        kalshi_yes_price = kalshi_market["yes_price"]
        legs = [
            {
                "platform": "Kalshi",
                "side": "YES",
                "market": kalshi_market["market_question"],
                "price": kalshi_yes_price,
                "fee": strategy["yes_fee"],
                "total": round(kalshi_yes_price + strategy["yes_fee"], 5),
            },
            {
                "platform": "Polymarket",
                "side": "NO",
                "market": poly_market["market_question"],
                "price": poly_market["no_price"],
                "fee": strategy["no_fee"],
                "total": round(poly_market["no_price"] + strategy["no_fee"], 5),
            },
        ]
        summary = "Buy YES on Kalshi and NO on Polymarket"

    return {
        "type": "cross_platform",
        "summary": summary,
        "strategy": strategy_key,
        "legs": legs,
    }


def format_buy_plan(buy_plan):
    """Format a buy plan for console output."""
    lines = [buy_plan["summary"]]
    for leg in buy_plan["legs"]:
        market_label = f" | {leg['market']}" if leg.get("market") else ""
        lines.append(
            f"  - {leg['platform']} {leg['side']}{market_label}: "
            f"price ${leg['price']:.4f}, fee ${leg['fee']:.4f}, "
            f"total ${leg['total']:.4f}"
        )
    return "\n".join(lines)


def total_two_leg_cost(yes_price, no_price, yes_fee, no_fee):
    """Total upfront cost to buy both YES and NO, including fees."""
    return yes_price + no_price + yes_fee + no_fee


def internal_arbitrage_profit(yes_price, no_price, yes_fee, no_fee):
    """
    Profit from buying both sides when one side must pay $1 at settlement.

    Positive profit means cost + fees is less than the guaranteed $1 payout.
    """
    return 1.0 - total_two_leg_cost(yes_price, no_price, yes_fee, no_fee)


def kalshi_internal_cost(yes_price, no_price, ticker=None, contracts=1):
    """Total Kalshi cost for buying YES and NO on the same market."""
    fee_multiplier = kalshi_fee_multiplier(ticker)
    yes_fee = kalshi_taker_fee(yes_price, contracts, fee_multiplier)
    no_fee = kalshi_taker_fee(no_price, contracts, fee_multiplier)
    return {
        "yes_fee": yes_fee,
        "no_fee": no_fee,
        "total_cost": total_two_leg_cost(yes_price, no_price, yes_fee, no_fee),
        "profit": internal_arbitrage_profit(yes_price, no_price, yes_fee, no_fee),
        "fee_multiplier": fee_multiplier,
        "buy_plan": build_internal_buy_plan("Kalshi", yes_price, no_price, yes_fee, no_fee),
    }


def polymarket_internal_cost(yes_price, no_price, fee_rate, contracts=1):
    """Total Polymarket cost for buying YES and NO on the same market."""
    yes_fee = polymarket_taker_fee(yes_price, fee_rate, contracts)
    no_fee = polymarket_taker_fee(no_price, fee_rate, contracts)
    return {
        "yes_fee": yes_fee,
        "no_fee": no_fee,
        "total_cost": total_two_leg_cost(yes_price, no_price, yes_fee, no_fee),
        "profit": internal_arbitrage_profit(yes_price, no_price, yes_fee, no_fee),
        "fee_rate": fee_rate,
        "buy_plan": build_internal_buy_plan("Polymarket", yes_price, no_price, yes_fee, no_fee),
    }


def cross_platform_cost(
    poly_yes_price,
    poly_no_price,
    poly_fee_rate,
    kalshi_yes_price,
    kalshi_no_price,
    kalshi_ticker=None,
    contracts=1,
):
    """
    Compare both cross-platform hedges for a matched market pair.

    Strategy A: buy YES on Polymarket + NO on Kalshi
    Strategy B: buy YES on Kalshi + NO on Polymarket
    """
    kalshi_multiplier = kalshi_fee_multiplier(kalshi_ticker)

    strategy_a = {
        "strategy": "buy_yes_polymarket_buy_no_kalshi",
        "yes_fee": polymarket_taker_fee(poly_yes_price, poly_fee_rate, contracts),
        "no_fee": kalshi_taker_fee(kalshi_no_price, contracts, kalshi_multiplier),
        "total_cost": total_two_leg_cost(
            poly_yes_price,
            kalshi_no_price,
            polymarket_taker_fee(poly_yes_price, poly_fee_rate, contracts),
            kalshi_taker_fee(kalshi_no_price, contracts, kalshi_multiplier),
        ),
    }
    strategy_a["profit"] = 1.0 - strategy_a["total_cost"]

    strategy_b = {
        "strategy": "buy_yes_kalshi_buy_no_polymarket",
        "yes_fee": kalshi_taker_fee(kalshi_yes_price, contracts, kalshi_multiplier),
        "no_fee": polymarket_taker_fee(poly_no_price, poly_fee_rate, contracts),
        "total_cost": total_two_leg_cost(
            kalshi_yes_price,
            poly_no_price,
            kalshi_taker_fee(kalshi_yes_price, contracts, kalshi_multiplier),
            polymarket_taker_fee(poly_no_price, poly_fee_rate, contracts),
        ),
    }
    strategy_b["profit"] = 1.0 - strategy_b["total_cost"]

    best = strategy_a if strategy_a["profit"] >= strategy_b["profit"] else strategy_b
    return {
        "strategy_a": strategy_a,
        "strategy_b": strategy_b,
        "best_strategy": best,
    }


# ForecastEx: ~$0.01 per contract built into spread (yes + no ≈ $1.01).
FORECASTEX_SPREAD_PREMIUM = 0.01


def forecastex_internal_cost(yes_price, no_price):
    """ForecastEx books often sum slightly above $1 due to embedded fees."""
    total = yes_price + no_price + FORECASTEX_SPREAD_PREMIUM
    return {
        "yes_fee": 0.0,
        "no_fee": 0.0,
        "spread_premium": FORECASTEX_SPREAD_PREMIUM,
        "total_cost": round(total, 5),
        "profit": round(1.0 - total, 5),
        "buy_plan": build_internal_buy_plan("ForecastEx", yes_price, no_price, 0.0, 0.0),
    }


def _venue_leg_fees(platform, side, price, market=None, contracts=1):
    """Return fee for one leg on a supported venue."""
    platform_key = (platform or "").lower()
    if platform_key == "kalshi":
        ticker = (market or {}).get("ticker")
        mult = (market or {}).get("fee_multiplier") or kalshi_fee_multiplier(ticker)
        return kalshi_taker_fee(price, contracts, mult)
    if platform_key == "polymarket":
        fee_rate = (market or {}).get("fee_rate", 0.0)
        return polymarket_taker_fee(price, fee_rate, contracts)
    if platform_key == "forecastex":
        return 0.0
    return 0.0


def two_venue_arbitrage_cost(market_a, market_b, platform_a, platform_b, contracts=1):
    """
    Compare both cross-venue hedges between two matched binary markets.

    Strategy 1: YES on A + NO on B
    Strategy 2: YES on B + NO on A
    """
    def leg_cost(yes_market, yes_platform, no_market, no_platform):
        yes_price = yes_market["yes_price"]
        no_price = no_market["no_price"]
        yes_fee = _venue_leg_fees(yes_platform, "YES", yes_price, yes_market, contracts)
        no_fee = _venue_leg_fees(no_platform, "NO", no_price, no_market, contracts)
        spread = 0.0
        if yes_platform.lower() == "forecastex":
            spread += FORECASTEX_SPREAD_PREMIUM / 2
        if no_platform.lower() == "forecastex":
            spread += FORECASTEX_SPREAD_PREMIUM / 2
        total = yes_price + no_price + yes_fee + no_fee + spread
        return {
            "yes_fee": yes_fee,
            "no_fee": no_fee,
            "spread_premium": spread,
            "total_cost": round(total, 5),
            "profit": round(1.0 - total, 5),
        }

    strategy_1 = {
        "strategy": f"buy_yes_{platform_a.lower()}_buy_no_{platform_b.lower()}",
        **leg_cost(market_a, platform_a, market_b, platform_b),
    }
    strategy_2 = {
        "strategy": f"buy_yes_{platform_b.lower()}_buy_no_{platform_a.lower()}",
        **leg_cost(market_b, platform_b, market_a, platform_a),
    }

    best = strategy_1 if strategy_1["profit"] >= strategy_2["profit"] else strategy_2
    return {
        "strategy_a": strategy_1,
        "strategy_b": strategy_2,
        "best_strategy": best,
    }


def build_two_venue_buy_plan(strategy_key, market_a, market_b, platform_a, platform_b, strategy):
    """Human-readable buy plan for any two venues."""
    if strategy_key.startswith(f"buy_yes_{platform_a.lower()}"):
        yes_market, yes_platform = market_a, platform_a
        no_market, no_platform = market_b, platform_b
    else:
        yes_market, yes_platform = market_b, platform_b
        no_market, no_platform = market_a, platform_b

    legs = [
        {
            "platform": yes_market.get("platform", yes_platform),
            "side": "YES",
            "market": yes_market.get("market_question"),
            "price": yes_market["yes_price"],
            "fee": strategy["yes_fee"],
            "total": round(yes_market["yes_price"] + strategy["yes_fee"], 5),
        },
        {
            "platform": no_market.get("platform", no_platform),
            "side": "NO",
            "market": no_market.get("market_question"),
            "price": no_market["no_price"],
            "fee": strategy["no_fee"],
            "total": round(no_market["no_price"] + strategy["no_fee"], 5),
        },
    ]
    if strategy.get("spread_premium"):
        legs[0]["spread_note"] = f"ForecastEx spread premium ~${strategy['spread_premium']:.3f}"

    return {
        "type": "cross_venue",
        "summary": (
            f"Buy YES on {legs[0]['platform']} and NO on {legs[1]['platform']}"
        ),
        "strategy": strategy_key,
        "legs": legs,
    }
