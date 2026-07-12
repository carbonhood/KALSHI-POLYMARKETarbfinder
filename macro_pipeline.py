# Macro arbitrage pipeline orchestration.
import json
from pathlib import Path

import forecastex_data
import kalshi_data
import polymarket_data
from config import (
    FORECASTEX_USE_IBKR_GATEWAY,
    MACRO_MAX_DAYS_TO_RESOLUTION,
    MAX_MACRO_HOLD_DAYS,
    MIN_MACRO_ANNUALIZED_RETURN,
    MIN_MACRO_PROFIT,
    SCAN_FORECASTEX,
    SCAN_KALSHI,
    SCAN_POLYMARKET,
    scan_horizon_days,
)
from macro_arb import scan_macro_arbitrage


def fetch_all_macro_data(quiet=False):
    """Download fresh market data from all enabled venues."""
    horizon = scan_horizon_days()
    if SCAN_KALSHI:
        if not quiet:
            print("Fetching Kalshi markets...")
        kalshi_data.fetch_kalshi_data(max_days=horizon)
        kalshi_data.fetch_priority_series(max_days=horizon)
        kalshi_data.fetch_politics_state_series()

    if SCAN_POLYMARKET:
        if not quiet:
            print("Fetching Polymarket markets...")
        polymarket_data.fetch_all_category_polymarket_data(max_days=horizon)

    if SCAN_FORECASTEX and FORECASTEX_USE_IBKR_GATEWAY:
        if not quiet:
            print("Fetching ForecastEx via IBKR gateway...")
        try:
            forecastex_data.fetch_from_ibkr_gateway()
        except ConnectionError as exc:
            if not quiet:
                print(f"  {exc}")


def extract_all_macro_markets(quiet=False):
    """Normalize raw payloads into clean market lists."""
    kalshi = []
    poly = []
    fex = []

    horizon = scan_horizon_days()
    if SCAN_KALSHI:
        kalshi_data.extract_kalshi_details(max_days=horizon, macro_days=MACRO_MAX_DAYS_TO_RESOLUTION)
        kalshi = list(kalshi_data.clean_markets_kalshi)

        if SCAN_POLYMARKET:
            if not quiet:
                print("Supplementing Polymarket from Kalshi queries...")
            polymarket_data.supplement_from_kalshi_searches(
                kalshi_data.clean_markets_kalshi,
                max_days=horizon,
            )

    if SCAN_POLYMARKET:
        polymarket_data.extract_polymarket_details(max_days=horizon)
        poly = list(polymarket_data.clean_markets_polymarket)

    if SCAN_FORECASTEX:
        forecastex_data.extract_forecastex_details(use_gateway=FORECASTEX_USE_IBKR_GATEWAY)
        fex = list(forecastex_data.clean_markets_forecastex)

    return kalshi, poly, fex


def run_macro_scan(quiet=False, use_cached=False):
    """
    Full pipeline: fetch (optional), extract, match, arb, rank.

    Returns scan result dict with opportunities ranked by score.
    """
    if not use_cached:
        fetch_all_macro_data(quiet=quiet)

    kalshi, poly, fex = extract_all_macro_markets(quiet=quiet)

    if not quiet:
        print("\nMatching macro markets across venues...")

    result = scan_macro_arbitrage(
        kalshi,
        poly,
        fex,
        max_hold_days=MAX_MACRO_HOLD_DAYS,
        min_profit=MIN_MACRO_PROFIT,
        min_annualized_return=MIN_MACRO_ANNUALIZED_RETURN,
        quiet=quiet,
    )

    if not quiet:
        print(f"\nMatched pairs: {len(result['pairs'])}")
        print(f"Macro arb opportunities (after filters): {len(result['opportunities'])}")

    return result


def save_macro_results(result, path="macro_arb_results.json"):
    """Persist scan output for research / monitoring."""

    def _slim_market(market):
        if not market:
            return {}
        return {
            key: value
            for key, value in market.items()
            if not key.startswith("_") and key not in ("tags",)
        }

    def _slim_opportunity(opp):
        slim = {k: v for k, v in opp.items() if k not in ("market_a", "market_b", "strategy_a", "strategy_b")}
        slim["market_a"] = _slim_market(opp.get("market_a"))
        slim["market_b"] = _slim_market(opp.get("market_b"))
        return slim

    output = {
        "macro_market_counts": {
            "kalshi": len(result.get("kalshi_macro", [])),
            "polymarket": len(result.get("polymarket_macro", [])),
            "forecastex": len(result.get("forecastex_macro", [])),
        },
        "matched_pairs": len(result.get("pairs", [])),
        "opportunity_count": len(result.get("opportunities", [])),
        "opportunities": [_slim_opportunity(o) for o in result.get("opportunities", [])],
        "matched_pair_summaries": [
            {
                "event_label": pair.get("event_label"),
                "match_method": pair.get("match_method"),
                "confidence": pair.get("confidence"),
                "platform_a": pair.get("platform_a"),
                "platform_b": pair.get("platform_b"),
                "market_a": pair["market_a"].get("market_question"),
                "market_b": pair["market_b"].get("market_question"),
            }
            for pair in result.get("pairs", [])
        ],
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2)
    return Path(path)
