# Macro event arbitrage scanner — Kalshi, Polymarket, ForecastEx.
import json
from pathlib import Path

from config import (
    ENABLED_CATEGORIES,
    MAX_MACRO_HOLD_DAYS,
    MIN_MACRO_ANNUALIZED_RETURN,
    MIN_MACRO_PROFIT,
    SCAN_FORECASTEX,
    SCAN_KALSHI,
    SCAN_POLYMARKET,
)
from macro_pipeline import run_macro_scan, save_macro_results


def _safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _print_opportunity(opp, index):
    _safe_print(f"\n#{index} [{opp['platform_a']} x {opp['platform_b']}] "
                f"profit ${opp['profit']:.4f} | "
                f"hold {opp['hold_days']:.1f}d | "
                f"ann. {opp['annualized_return_pct']:.1f}% | "
                f"score {opp['score']:.2f}")
    if opp.get("event_label"):
        _safe_print(f"  Event: {opp['event_label']} ({opp.get('match_method')}, conf {opp.get('confidence', 0):.2f})")
    _safe_print(f"  A: {opp['market_a']['market_question'][:90]}")
    _safe_print(f"  B: {opp['market_b']['market_question'][:90]}")
    _safe_print(f"  Plan: {opp['buy_plan']['summary']}")
    for leg in opp["buy_plan"]["legs"]:
        _safe_print(
            f"    - {leg['platform']} {leg['side']}: "
            f"${leg['price']:.4f} + fee ${leg.get('fee', 0):.4f} = ${leg['total']:.4f}"
        )


def main(use_cached=False):
    _safe_print("=" * 60)
    _safe_print("Macro Arbitrage Finder")
    _safe_print("Venues: "
                f"{'Kalshi ' if SCAN_KALSHI else ''}"
                f"{'Polymarket ' if SCAN_POLYMARKET else ''}"
                f"{'ForecastEx' if SCAN_FORECASTEX else ''}")
    _safe_print(f"Categories: {', '.join(ENABLED_CATEGORIES)}")
    _safe_print(f"Filters: min profit ${MIN_MACRO_PROFIT:.3f} | "
                f"max hold {MAX_MACRO_HOLD_DAYS}d | "
                f"min annualized {MIN_MACRO_ANNUALIZED_RETURN * 100:.0f}%")
    _safe_print("=" * 60 + "\n")

    result = run_macro_scan(quiet=False, use_cached=use_cached)
    path = save_macro_results(result)

    opps = result["opportunities"]
    _safe_print(f"\n{'=' * 60}")
    _safe_print(f"OPPORTUNITIES: {len(opps)} (ranked by score = ann. return x confidence)")
    _safe_print(f"Results saved to {path}")

    for idx, opp in enumerate(opps[:25], start=1):
        _print_opportunity(opp, idx)
    if len(opps) > 25:
        _safe_print(f"\n  ... and {len(opps) - 25} more in {path}")

    if not opps:
        _safe_print("\nNo macro arbs passed filters. Next steps:")
        _safe_print("  - Lower MIN_MACRO_ANNUALIZED_RETURN in config.py for research mode")
        _safe_print("  - Add ForecastEx data to forecastex_data.json or enable IBKR gateway")
        _safe_print("  - Extend crosswalk.json for known macro event mappings")
        _safe_print("  - Run log_macro_arb.py to monitor as prices move")

    # Also print matched pairs without arb (research signal).
    pairs = result["pairs"]
    arb_pair_keys = {
        (p["market_a"]["market_question"], p["market_b"]["market_question"])
        for p in opps
    }
    research_pairs = [
        p for p in pairs
        if (p["market_a"]["market_question"], p["market_b"]["market_question"]) not in arb_pair_keys
    ]
    if research_pairs:
        _safe_print(f"\nMATCHED PAIRS WITHOUT ARB ({len(research_pairs)}) — watchlist:")
        for pair in research_pairs[:10]:
            _safe_print(f"  [{pair.get('confidence', 0):.2f}] {pair.get('event_label', 'event')}")
            _safe_print(f"    {pair['platform_a']}: {pair['market_a']['market_question'][:70]}")
            _safe_print(f"    {pair['platform_b']}: {pair['market_b']['market_question'][:70]}")

    return result


if __name__ == "__main__":
    import sys
    cached = "--cached" in sys.argv
    main(use_cached=cached)
