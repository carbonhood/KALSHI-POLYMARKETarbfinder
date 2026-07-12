# Looks for arbitrage opportunities after including platform trading fees.
from polymarket_data import clean_markets_polymarket
from kalshi_data import clean_markets_kalshi
from fees import (
    build_cross_platform_buy_plan,
    cross_platform_cost,
    format_buy_plan,
    kalshi_internal_cost,
    polymarket_internal_cost,
)

internal_arbitrage_opportunities_polymarket = []
internal_arbitrage_opportunities_kalshi = []
cross_platform_arbitrage_opportunities = []


def _safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _print_opportunity(market_label, cost_details):
    _safe_print(f"Arbitrage opportunity found for market: {market_label}")
    _safe_print(format_buy_plan(cost_details["buy_plan"]))
    _safe_print(
        f"Total cost: ${cost_details['total_cost']:.5f}, "
        f"Expected profit: ${cost_details['profit']:.5f}"
    )
    _safe_print("--------------------------------")


def find_internal_arbitrage_opportunities_polymarket(quiet=False):
    """
    Internal arbitrage happens when buying both YES and NO costs less than $1
    after taker fees. One side must pay out $1 at settlement.
    """
    internal_arbitrage_opportunities_polymarket.clear()
    for market in clean_markets_polymarket:
        cost_details = polymarket_internal_cost(
            market["yes_price"],
            market["no_price"],
            market.get("fee_rate", 0.0),
        )
        if cost_details["profit"] > 0:
            opportunity = {
                "type": "internal_polymarket",
                **market,
                **cost_details,
            }
            if not quiet:
                _print_opportunity(market["market_question"], cost_details)
            internal_arbitrage_opportunities_polymarket.append(opportunity)

    if not quiet:
        print(
            "Total internal arbitrage opportunities found for Polymarket: "
            f"{len(internal_arbitrage_opportunities_polymarket)}"
        )
    return internal_arbitrage_opportunities_polymarket


def find_internal_arbitrage_opportunities_kalshi(quiet=False):
    """Same internal arbitrage check, but for Kalshi markets."""
    internal_arbitrage_opportunities_kalshi.clear()
    for market in clean_markets_kalshi:
        cost_details = kalshi_internal_cost(
            market["yes_price"],
            market["no_price"],
            market.get("ticker"),
        )
        if cost_details["profit"] > 0:
            opportunity = {
                "type": "internal_kalshi",
                **market,
                **cost_details,
            }
            if not quiet:
                _print_opportunity(market["market_question"], cost_details)
            internal_arbitrage_opportunities_kalshi.append(opportunity)

    if not quiet:
        print(
            "Total internal arbitrage opportunities found for Kalshi: "
            f"{len(internal_arbitrage_opportunities_kalshi)}"
        )
    return internal_arbitrage_opportunities_kalshi


def find_cross_platform_arbitrage_opportunities(matched_markets, quiet=False):
    """
    Check matched Polymarket/Kalshi pairs for cross-platform arbitrage
    after including both platforms' taker fees.
    """
    cross_platform_arbitrage_opportunities.clear()

    for pair in matched_markets:
        poly_market = pair["polymarket"]
        kalshi_market = pair["kalshi"]
        arb_details = cross_platform_cost(
            poly_market["yes_price"],
            poly_market["no_price"],
            poly_market.get("fee_rate", 0.0),
            kalshi_market["yes_price"],
            kalshi_market["no_price"],
            kalshi_market.get("ticker"),
        )
        best = arb_details["best_strategy"]
        if best["profit"] <= 0:
            continue

        buy_plan = build_cross_platform_buy_plan(
            best["strategy"],
            poly_market,
            kalshi_market,
            best,
        )
        opportunity = {
            "type": "cross_platform",
            "polymarket": poly_market,
            "kalshi": kalshi_market,
            "strategy": best["strategy"],
            "yes_fee": best["yes_fee"],
            "no_fee": best["no_fee"],
            "total_cost": best["total_cost"],
            "profit": best["profit"],
            "buy_plan": buy_plan,
            "strategy_a": arb_details["strategy_a"],
            "strategy_b": arb_details["strategy_b"],
            "event_label": pair.get("event_label"),
            "event_type": pair.get("event_type"),
            "match_method": pair.get("match_method"),
            "polymarket_outcome": pair.get("polymarket_outcome"),
            "kalshi_outcome": pair.get("kalshi_outcome"),
        }
        if not quiet:
            _safe_print("Cross-platform arbitrage opportunity found:")
            if pair.get("event_label"):
                _safe_print(f"  Event: {pair['event_label']}")
            _safe_print(f"  Polymarket: {poly_market['market_question']}")
            _safe_print(f"  Kalshi: {kalshi_market['market_question']}")
            if pair.get("polymarket_outcome") or pair.get("kalshi_outcome"):
                _safe_print(
                    f"  Outcome: {pair.get('polymarket_outcome')} "
                    f"(Poly) = {pair.get('kalshi_outcome')} (Kalshi)"
                )
            _safe_print(format_buy_plan(buy_plan))
            _safe_print(
                f"Total cost: ${best['total_cost']:.5f}, "
                f"Expected profit: ${best['profit']:.5f}"
            )
            _safe_print("--------------------------------")
        cross_platform_arbitrage_opportunities.append(opportunity)

    if not quiet:
        print(
            "Total cross-platform arbitrage opportunities found: "
            f"{len(cross_platform_arbitrage_opportunities)}"
        )
    return cross_platform_arbitrage_opportunities


def scan_all_opportunities(matched_markets):
    """Return all current arbitrage opportunities without printing."""
    internal_polymarket = find_internal_arbitrage_opportunities_polymarket(quiet=True)
    internal_kalshi = find_internal_arbitrage_opportunities_kalshi(quiet=True)
    cross_platform = find_cross_platform_arbitrage_opportunities(matched_markets, quiet=True)
    return {
        "internal_polymarket": internal_polymarket,
        "internal_kalshi": internal_kalshi,
        "cross_platform": cross_platform,
    }


def find_internal_arbitrage_opportunities():
    """Run the internal arbitrage scan on both platforms."""
    find_internal_arbitrage_opportunities_polymarket()
    find_internal_arbitrage_opportunities_kalshi()
    return internal_arbitrage_opportunities_polymarket + internal_arbitrage_opportunities_kalshi
