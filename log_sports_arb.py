# Poll sports arbitrage opportunities on an interval.
#
#   python log_sports_arb.py
#   python log_sports_arb.py --interval 60 --cycles 10

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from config import MIN_SPORTS_ARB_PROFIT
from sports_arb import (
    filter_kalshi_sports_markets,
    find_cross_book_arbs,
    find_kalshi_vs_book_arbs,
)
from sports_odds import fetch_all_odds, get_api_key, load_cached_odds

import kalshi_data

LOG_DIR = Path("logs")


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_scan(use_cache=False):
    api_key = get_api_key()
    if api_key and not use_cache:
        payload = fetch_all_odds(api_key)
        odds_events = payload["events"]
    else:
        odds_events = load_cached_odds().get("events", [])

    cross_book = find_cross_book_arbs(odds_events) if odds_events else []

    kalshi_book = []
    if odds_events:
        kalshi_data.fetch_kalshi_data_with_priorities()
        kalshi_data.extract_kalshi_details()
        sports = filter_kalshi_sports_markets(kalshi_data.clean_markets_kalshi)
        kalshi_book = find_kalshi_vs_book_arbs(sports, odds_events)

    return {
        "timestamp": utc_now_iso(),
        "cross_book_count": len(cross_book),
        "kalshi_vs_book_count": len(kalshi_book),
        "cross_book": cross_book,
        "kalshi_vs_book": kalshi_book,
    }


def main():
    parser = argparse.ArgumentParser(description="Log sports arbitrage snapshots")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between scans")
    parser.add_argument("--cycles", type=int, default=0, help="Max cycles (0 = infinite)")
    parser.add_argument("--cache-only", action="store_true", help="Use sports_odds.json only")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    session_path = LOG_DIR / f"sports_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    snapshots = []

    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- Scan {cycle} @ {utc_now_iso()} ---")
        try:
            snapshot = run_scan(use_cache=args.cache_only)
        except Exception as exc:
            print(f"Scan failed: {exc}")
            snapshot = {"timestamp": utc_now_iso(), "error": str(exc)}

        snapshots.append(snapshot)
        with open(session_path, "w", encoding="utf-8") as file:
            json.dump(snapshots, file, indent=2)

        cb = snapshot.get("cross_book_count", 0)
        kb = snapshot.get("kalshi_vs_book_count", 0)
        print(f"Found {cb} cross-book + {kb} Kalshi-vs-book (min profit ${MIN_SPORTS_ARB_PROFIT})")
        print(f"Session log: {session_path}")

        if args.cycles and cycle >= args.cycles:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
