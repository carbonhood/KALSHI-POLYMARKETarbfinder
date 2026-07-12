# Build JSON payloads for the scan-data branch (GitHub Actions + Netlify dashboard).
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    ENABLED_CATEGORIES,
    FORECASTEX_USE_IBKR_GATEWAY,
    KALSHI_MAX_MARKETS,
    MACRO_MAX_DAYS_TO_RESOLUTION,
    MAX_HOLD_DAYS_BY_CATEGORY,
    MAX_MACRO_HOLD_DAYS,
    MIN_MACRO_ANNUALIZED_RETURN,
    MIN_MACRO_PROFIT,
    POLITICS_MAX_DAYS_TO_RESOLUTION,
    POLYMARKET_MAX_EVENTS,
    SCAN_FORECASTEX,
    SCAN_KALSHI,
    SCAN_POLYMARKET,
    scan_horizon_days,
)
from macro_pipeline import run_macro_scan, save_macro_results

MAX_HISTORY = 500
PUBLISH_DIR = _ROOT / "publish-data"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def config_snapshot():
    return {
        "version": "1.2",
        "venues": {
            "kalshi": SCAN_KALSHI,
            "polymarket": SCAN_POLYMARKET,
            "forecastex": SCAN_FORECASTEX,
            "forecastex_ibkr": FORECASTEX_USE_IBKR_GATEWAY,
        },
        "categories": list(ENABLED_CATEGORIES),
        "limits": {
            "kalshi_max_markets": KALSHI_MAX_MARKETS,
            "polymarket_max_events": POLYMARKET_MAX_EVENTS,
            "scan_horizon_days": scan_horizon_days(),
            "macro_horizon_days": MACRO_MAX_DAYS_TO_RESOLUTION,
            "politics_horizon_days": POLITICS_MAX_DAYS_TO_RESOLUTION,
        },
        "hold_days_by_category": MAX_HOLD_DAYS_BY_CATEGORY,
        "filters": {
            "min_profit": MIN_MACRO_PROFIT,
            "min_annualized_return": MIN_MACRO_ANNUALIZED_RETURN,
            "max_macro_hold_days": MAX_MACRO_HOLD_DAYS,
        },
    }


def slim_results(result):
    """Same shape as save_macro_results for Netlify dashboard."""

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

    return {
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


def load_prior_history(prior_dir):
    history_path = Path(prior_dir) / "scan_history.json"
    if not history_path.exists():
        return []
    try:
        return json.loads(history_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def main():
    parser = argparse.ArgumentParser(description="Run scan and write publish-data/ for scan-data branch")
    parser.add_argument("--cached", action="store_true", help="Use cached API JSON (faster, for testing)")
    parser.add_argument("--prior-dir", default="", help="Prior scan-data branch checkout for history merge")
    args = parser.parse_args()

    started = utc_now_iso()
    error = None
    result = None

    try:
        result = run_macro_scan(quiet=True, use_cached=args.cached)
        save_macro_results(result, path="macro_arb_results.json")
    except Exception as exc:
        error = str(exc)
        print(f"Scan failed: {exc}", file=sys.stderr)

    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    if result:
        payload = slim_results(result)
        payload["scanned_at"] = started
        (PUBLISH_DIR / "macro_arb_latest.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        top = result["opportunities"][0] if result.get("opportunities") else None
        history_entry = {
            "timestamp": started,
            "opportunity_count": len(result.get("opportunities", [])),
            "matched_pairs": len(result.get("pairs", [])),
            "market_counts": {
                "kalshi": len(result.get("kalshi_macro", [])),
                "polymarket": len(result.get("polymarket_macro", [])),
            },
            "top_profit": top.get("profit") if top else None,
            "top_event": top.get("event_label") if top else None,
            "error": None,
        }
    else:
        (PUBLISH_DIR / "macro_arb_latest.json").write_text(
            json.dumps(
                {
                    "macro_market_counts": {},
                    "matched_pairs": 0,
                    "opportunity_count": 0,
                    "opportunities": [],
                    "matched_pair_summaries": [],
                    "scanned_at": started,
                    "error": error,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        history_entry = {
            "timestamp": started,
            "opportunity_count": 0,
            "matched_pairs": 0,
            "market_counts": {},
            "top_profit": None,
            "top_event": None,
            "error": error,
        }

    history = load_prior_history(args.prior_dir) if args.prior_dir else []
    history.append(history_entry)
    history = history[-MAX_HISTORY:]

    meta = {
        "last_scan_started": started,
        "last_scan_finished": utc_now_iso(),
        "last_error": error,
        "scan_mode": "cached" if args.cached else "fresh",
        "scans_in_history": len(history),
        "github_actions": True,
    }

    (PUBLISH_DIR / "scan_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (PUBLISH_DIR / "scan_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (PUBLISH_DIR / "config_snapshot.json").write_text(
        json.dumps(config_snapshot(), indent=2),
        encoding="utf-8",
    )

    print(f"Published to {PUBLISH_DIR}/")
    if result:
        print(
            f"  opportunities={len(result['opportunities'])} "
            f"pairs={len(result['pairs'])}"
        )
    if error:
        print(f"Scan completed with error (metadata still published): {error}", file=sys.stderr)
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
