#!/usr/bin/env python3
"""On-demand LLM extraction to populate llm_extraction_cache.sqlite (scans read cache only)."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import LLM_CACHE_PATH, LLM_MODEL
from llm_extraction import enrich_markets, llm_available
from llm_extraction_cache import cache_stats, close_cache
from llm_market_payload import summarize_payload
from macro_pipeline import extract_all_macro_markets, fetch_all_macro_data


def _collect_markets():
    import forecastex_data
    import kalshi_data
    import polymarket_data
    from config import SCAN_FORECASTEX, SCAN_KALSHI, SCAN_POLYMARKET

    markets = []
    if SCAN_KALSHI:
        markets.extend(kalshi_data.clean_markets_kalshi)
    if SCAN_POLYMARKET:
        markets.extend(polymarket_data.clean_markets_polymarket)
    if SCAN_FORECASTEX:
        markets.extend(forecastex_data.clean_markets_forecastex)
    return markets


def _progress(index, total, market, result):
    status = result.get("status")
    print(f"[{index}/{total}] {status:18} {summarize_payload(market)}")
    if result.get("validation_errors"):
        for error in result["validation_errors"][:3]:
            print(f"    ! {error}")


def main():
    parser = argparse.ArgumentParser(
        description="Populate LLM extraction cache for markets regex parsers miss."
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use cached kalshi_data.json / polymarket_data.json (skip API fetch)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even when cache entry exists",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include markets that already have regex event_key (default: gaps only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of markets to send to the LLM this run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidates only; do not call the LLM",
    )
    args = parser.parse_args()

    if not args.cached:
        print("Fetching fresh venue data...")
        fetch_all_macro_data(quiet=False)
    else:
        print("Using cached venue JSON files...")

    print("Extracting clean market lists...")
    extract_all_macro_markets(quiet=False)
    markets = _collect_markets()
    print(f"Loaded {len(markets)} normalized markets")

    before = cache_stats()
    print(f"Cache before: {before['valid']} valid / {before['total']} total at {LLM_CACHE_PATH}")

    if args.dry_run:
        from outcome_normalization import extract_event_key
        from llm_extraction_cache import get_cached_record

        candidates = []
        for market in markets:
            if args.all or args.force:
                candidates.append(market)
                continue
            if extract_event_key(market) is not None:
                continue
            if not args.force and get_cached_record(market) is not None:
                continue
            candidates.append(market)

        if args.limit is not None:
            candidates = candidates[: args.limit]

        print(f"Dry run: would enrich {len(candidates)} markets")
        for market in candidates[:25]:
            print(f"  - {summarize_payload(market)}")
        if len(candidates) > 25:
            print(f"  ... and {len(candidates) - 25} more")
        return 0

    if not llm_available():
        print("ERROR: OPENAI_API_KEY is not set. Export it before running enrichment.")
        return 1

    print(f"Enriching with model {LLM_MODEL}...")
    stats = enrich_markets(
        markets,
        force=args.force,
        only_missing=not args.all,
        limit=args.limit,
        progress_callback=_progress,
    )

    after = cache_stats()
    print("\nEnrichment summary:")
    for key, value in stats.items():
        if key != "error_samples":
            print(f"  {key}: {value}")
    if stats.get("error_samples"):
        print("  sample errors:")
        for sample in stats["error_samples"]:
            print(f"    - {sample}")

    print(f"\nCache after: {after['valid']} valid / {after['total']} total")
    print(f"By platform: {after.get('by_platform')}")
    close_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
