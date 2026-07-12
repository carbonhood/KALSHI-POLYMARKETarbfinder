# Continuous macro arb monitoring.
#
#   python log_macro_arb.py
#   python log_macro_arb.py --interval 120 --cycles 20
#   python log_macro_arb.py --cached

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from macro_pipeline import run_macro_scan, save_macro_results

LOG_DIR = Path("logs")


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description="Monitor macro arbitrage opportunities")
    parser.add_argument("--interval", type=int, default=120, help="Seconds between scans")
    parser.add_argument("--cycles", type=int, default=0, help="Max cycles (0 = infinite)")
    parser.add_argument("--cached", action="store_true", help="Use cached JSON without re-fetching")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    session_path = LOG_DIR / f"macro_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    snapshots = []

    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- Macro scan {cycle} @ {utc_now_iso()} ---")
        try:
            result = run_macro_scan(quiet=True, use_cached=args.cached)
            save_macro_results(result, path=LOG_DIR / "macro_arb_latest.json")
            snapshot = {
                "timestamp": utc_now_iso(),
                "opportunity_count": len(result["opportunities"]),
                "matched_pairs": len(result["pairs"]),
                "top_opportunity": result["opportunities"][0] if result["opportunities"] else None,
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
                    for pair in result.get("pairs", [])[:50]
                ],
            }
        except Exception as exc:
            print(f"Scan failed: {exc}")
            snapshot = {"timestamp": utc_now_iso(), "error": str(exc)}

        snapshots.append(snapshot)
        with open(session_path, "w", encoding="utf-8") as file:
            json.dump(snapshots, file, indent=2)

        count = snapshot.get("opportunity_count", 0)
        pairs = snapshot.get("matched_pairs", 0)
        print(f"Found {count} opportunities from {pairs} matched pairs")
        print(f"Session log: {session_path}")

        if args.cycles and cycle >= args.cycles:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
