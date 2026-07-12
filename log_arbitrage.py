# Continuously discovers arbitrage opportunities and logs 30-second snapshots.
#
# Legacy Poly×Kalshi tracker. For multi-venue macro monitoring, prefer log_macro_arb.py.
#
# Run with:
#   python log_arbitrage.py
#   python log_arbitrage.py --cycles 5
#   python log_arbitrage.py --interval 30 --max-tracking-minutes 30

import argparse
import csv
import hashlib
import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import kalshi_data
import matching
import math_engine
import polymarket_data
from config import MAX_DAYS_TO_RESOLUTION
from fees import (
    build_cross_platform_buy_plan,
    cross_platform_cost,
    kalshi_internal_cost,
    polymarket_internal_cost,
)

LOG_DIR = Path("logs")
SNAPSHOT_INTERVAL_SECONDS = 30
MAX_TRACKING_SECONDS = 30 * 60


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_opportunity_id(opportunity):
    """Create a stable ID so the same arb is not logged twice in one session."""
    if opportunity["type"] == "internal_polymarket":
        key = f"poly:{opportunity['market_question']}"
    elif opportunity["type"] == "internal_kalshi":
        key = f"kalshi:{opportunity.get('ticker', opportunity['market_question'])}"
    else:
        key = (
            f"cross:{opportunity['polymarket']['market_question']}:"
            f"{opportunity['kalshi'].get('ticker', opportunity['kalshi']['market_question'])}:"
            f"{opportunity['strategy']}"
        )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def build_market_lookup():
    """Fast lookup tables for re-pricing tracked opportunities."""
    return {
        "polymarket_by_question": {
            market["market_question"]: market for market in polymarket_data.clean_markets_polymarket
        },
        "kalshi_by_ticker": {
            market["ticker"]: market for market in kalshi_data.clean_markets_kalshi
        },
        "kalshi_by_question": {
            market["market_question"]: market for market in kalshi_data.clean_markets_kalshi
        },
    }


def evaluate_opportunity(opportunity, lookup):
    """Recompute profit and prices for a tracked opportunity."""
    if opportunity["type"] == "internal_polymarket":
        market = lookup["polymarket_by_question"].get(opportunity["market_question"])
        if not market:
            return None
        cost = polymarket_internal_cost(
            market["yes_price"],
            market["no_price"],
            market.get("fee_rate", 0.0),
        )
        return {
            "still_valid": cost["profit"] > 0,
            "profit": cost["profit"],
            "total_cost": cost["total_cost"],
            "yes_fee": cost["yes_fee"],
            "no_fee": cost["no_fee"],
            "prices": {
                "polymarket_yes": market["yes_price"],
                "polymarket_no": market["no_price"],
            },
            "buy_plan": cost["buy_plan"],
        }

    if opportunity["type"] == "internal_kalshi":
        market = lookup["kalshi_by_ticker"].get(opportunity.get("ticker"))
        if not market:
            market = lookup["kalshi_by_question"].get(opportunity["market_question"])
        if not market:
            return None
        cost = kalshi_internal_cost(
            market["yes_price"],
            market["no_price"],
            market.get("ticker"),
        )
        return {
            "still_valid": cost["profit"] > 0,
            "profit": cost["profit"],
            "total_cost": cost["total_cost"],
            "yes_fee": cost["yes_fee"],
            "no_fee": cost["no_fee"],
            "prices": {
                "kalshi_yes": market["yes_price"],
                "kalshi_no": market["no_price"],
            },
            "buy_plan": cost["buy_plan"],
        }

    poly_market = lookup["polymarket_by_question"].get(
        opportunity["polymarket"]["market_question"]
    )
    kalshi_market = lookup["kalshi_by_ticker"].get(opportunity["kalshi"].get("ticker"))
    if not kalshi_market:
        kalshi_market = lookup["kalshi_by_question"].get(
            opportunity["kalshi"]["market_question"]
        )
    if not poly_market or not kalshi_market:
        return None

    arb_details = cross_platform_cost(
        poly_market["yes_price"],
        poly_market["no_price"],
        poly_market.get("fee_rate", 0.0),
        kalshi_market["yes_price"],
        kalshi_market["no_price"],
        kalshi_market.get("ticker"),
    )
    best = arb_details["best_strategy"]
    buy_plan = build_cross_platform_buy_plan(
        best["strategy"],
        poly_market,
        kalshi_market,
        best,
    )
    return {
        "still_valid": best["profit"] > 0,
        "profit": best["profit"],
        "total_cost": best["total_cost"],
        "yes_fee": best["yes_fee"],
        "no_fee": best["no_fee"],
        "strategy": best["strategy"],
        "prices": {
            "polymarket_yes": poly_market["yes_price"],
            "polymarket_no": poly_market["no_price"],
            "kalshi_yes": kalshi_market["yes_price"],
            "kalshi_no": kalshi_market["no_price"],
        },
        "buy_plan": buy_plan,
    }


def flatten_opportunity_for_log(opportunity):
    """Store the key fields from a discovered opportunity."""
    record = {
        "type": opportunity["type"],
        "profit": opportunity["profit"],
        "total_cost": opportunity["total_cost"],
        "yes_fee": opportunity["yes_fee"],
        "no_fee": opportunity["no_fee"],
        "buy_plan": opportunity["buy_plan"],
    }
    if opportunity["type"] == "cross_platform":
        record["polymarket"] = opportunity["polymarket"]
        record["kalshi"] = opportunity["kalshi"]
        record["strategy"] = opportunity["strategy"]
    else:
        record["market_question"] = opportunity["market_question"]
        record["yes_price"] = opportunity["yes_price"]
        record["no_price"] = opportunity["no_price"]
        if opportunity["type"] == "internal_polymarket":
            record["fee_rate"] = opportunity.get("fee_rate", 0.0)
        if opportunity["type"] == "internal_kalshi":
            record["ticker"] = opportunity.get("ticker")
    return record


def create_snapshot(tracked, evaluation, elapsed_seconds):
    return {
        "timestamp": utc_now_iso(),
        "elapsed_seconds": elapsed_seconds,
        "still_valid": evaluation["still_valid"],
        "profit": round(evaluation["profit"], 6),
        "total_cost": round(evaluation["total_cost"], 6),
        "yes_fee": evaluation["yes_fee"],
        "no_fee": evaluation["no_fee"],
        "prices": evaluation.get("prices", {}),
        "buy_plan": evaluation.get("buy_plan"),
        "strategy": evaluation.get("strategy"),
    }


class ArbitrageLogger:
    def __init__(
        self,
        snapshot_interval_seconds=SNAPSHOT_INTERVAL_SECONDS,
        max_tracking_seconds=MAX_TRACKING_SECONDS,
        log_dir=LOG_DIR,
    ):
        self.snapshot_interval_seconds = snapshot_interval_seconds
        self.max_tracking_seconds = max_tracking_seconds
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = self.log_dir / f"arb_session_{session_stamp}.json"
        self.csv_file = self.log_dir / f"arb_session_{session_stamp}.csv"
        self.master_file = self.log_dir / "arb_opportunities_master.json"

        self.session_data = {
            "session_started_at": utc_now_iso(),
            "last_updated_at": utc_now_iso(),
            "settings": {
                "snapshot_interval_seconds": snapshot_interval_seconds,
                "max_tracking_seconds": max_tracking_seconds,
                "max_days_to_resolution": MAX_DAYS_TO_RESOLUTION,
            },
            "opportunities": [],
        }
        self.active_trackers = {}

    def save(self):
        self.session_data["last_updated_at"] = utc_now_iso()
        with open(self.session_file, "w", encoding="utf-8") as file:
            json.dump(self.session_data, file, indent=4)

        self._write_csv()
        self._update_master_file()

    def _write_csv(self):
        rows = []
        fieldnames = [
            "opportunity_id",
            "type",
            "discovered_at",
            "status",
            "buy_summary",
            "market_question",
            "polymarket_question",
            "kalshi_question",
            "strategy",
            "snapshot_timestamp",
            "elapsed_seconds",
            "still_valid",
            "profit",
            "total_cost",
            "prices_json",
        ]

        for opportunity in self.session_data["opportunities"]:
            base = {
                "opportunity_id": opportunity["opportunity_id"],
                "type": opportunity["type"],
                "discovered_at": opportunity["discovered_at"],
                "status": opportunity["status"],
                "buy_summary": opportunity["discovery"]["buy_plan"]["summary"],
                "market_question": "",
                "polymarket_question": "",
                "kalshi_question": "",
                "strategy": "",
            }
            if opportunity["type"] == "cross_platform":
                base["polymarket_question"] = opportunity["discovery"]["polymarket"]["market_question"]
                base["kalshi_question"] = opportunity["discovery"]["kalshi"]["market_question"]
                base["strategy"] = opportunity["discovery"].get("strategy", "")
            else:
                base["market_question"] = opportunity["discovery"]["market_question"]

            for snapshot in opportunity["snapshots"]:
                rows.append(
                    {
                        **base,
                        "snapshot_timestamp": snapshot["timestamp"],
                        "elapsed_seconds": snapshot["elapsed_seconds"],
                        "still_valid": snapshot["still_valid"],
                        "profit": snapshot["profit"],
                        "total_cost": snapshot["total_cost"],
                        "prices_json": json.dumps(snapshot.get("prices", {})),
                    }
                )

        if not rows:
            return

        with open(self.csv_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _update_master_file(self):
        if self.master_file.exists():
            with open(self.master_file, "r", encoding="utf-8") as file:
                master = json.load(file)
        else:
            master = {"sessions": []}

        master["sessions"] = [
            session
            for session in master["sessions"]
            if session.get("session_file") != str(self.session_file)
        ]
        master["sessions"].append(
            {
                "session_started_at": self.session_data["session_started_at"],
                "last_updated_at": self.session_data["last_updated_at"],
                "session_file": str(self.session_file),
                "csv_file": str(self.csv_file),
                "opportunity_count": len(self.session_data["opportunities"]),
            }
        )
        with open(self.master_file, "w", encoding="utf-8") as file:
            json.dump(master, file, indent=4)

    def register_discoveries(self, discovered_opportunities):
        new_count = 0
        for opportunity in discovered_opportunities:
            opportunity_id = make_opportunity_id(opportunity)
            if opportunity_id in self.active_trackers:
                continue

            discovered_at = utc_now_iso()
            evaluation = {
                "still_valid": True,
                "profit": opportunity["profit"],
                "total_cost": opportunity["total_cost"],
                "yes_fee": opportunity["yes_fee"],
                "no_fee": opportunity["no_fee"],
                "buy_plan": opportunity["buy_plan"],
                "prices": self._prices_from_opportunity(opportunity),
                "strategy": opportunity.get("strategy"),
            }
            tracked = {
                "opportunity_id": opportunity_id,
                "type": opportunity["type"],
                "discovered_at": discovered_at,
                "status": "active",
                "closed_at": None,
                "close_reason": None,
                "discovery": flatten_opportunity_for_log(opportunity),
                "snapshots": [create_snapshot({}, evaluation, 0)],
            }
            self.session_data["opportunities"].append(tracked)
            self.active_trackers[opportunity_id] = {
                "record": tracked,
                "discovered_monotonic": time.monotonic(),
                "last_snapshot_monotonic": time.monotonic(),
            }
            new_count += 1
            print(
                f"[DISCOVERED] {opportunity_id} | {opportunity['type']} | "
                f"profit ${opportunity['profit']:.5f} | "
                f"{opportunity['buy_plan']['summary']}"
            )
        return new_count

    def _prices_from_opportunity(self, opportunity):
        if opportunity["type"] == "cross_platform":
            return {
                "polymarket_yes": opportunity["polymarket"]["yes_price"],
                "polymarket_no": opportunity["polymarket"]["no_price"],
                "kalshi_yes": opportunity["kalshi"]["yes_price"],
                "kalshi_no": opportunity["kalshi"]["no_price"],
            }
        if opportunity["type"] == "internal_polymarket":
            return {
                "polymarket_yes": opportunity["yes_price"],
                "polymarket_no": opportunity["no_price"],
            }
        return {
            "kalshi_yes": opportunity["yes_price"],
            "kalshi_no": opportunity["no_price"],
        }

    def update_snapshots(self, lookup):
        closed_count = 0
        now = time.monotonic()

        for opportunity_id, tracker in list(self.active_trackers.items()):
            record = tracker["record"]
            elapsed_seconds = int(now - tracker["discovered_monotonic"])
            evaluation = evaluate_opportunity(record["discovery"], lookup)

            if evaluation is None:
                self._close_tracker(opportunity_id, "market_not_found")
                closed_count += 1
                continue

            if now - tracker["last_snapshot_monotonic"] >= self.snapshot_interval_seconds:
                snapshot = create_snapshot(record, evaluation, elapsed_seconds)
                record["snapshots"].append(snapshot)
                tracker["last_snapshot_monotonic"] = now
                print(
                    f"[SNAPSHOT] {opportunity_id} | +{elapsed_seconds}s | "
                    f"valid={evaluation['still_valid']} | profit ${evaluation['profit']:.5f}"
                )

            if not evaluation["still_valid"]:
                self._close_tracker(opportunity_id, "no_longer_profitable")
                closed_count += 1
            elif elapsed_seconds >= self.max_tracking_seconds:
                self._close_tracker(opportunity_id, "max_tracking_reached")
                closed_count += 1

        return closed_count

    def _close_tracker(self, opportunity_id, reason):
        tracker = self.active_trackers.pop(opportunity_id)
        record = tracker["record"]
        record["status"] = "closed"
        record["closed_at"] = utc_now_iso()
        record["close_reason"] = reason
        print(f"[CLOSED] {opportunity_id} | reason={reason}")


def refresh_market_data(use_cached=False):
    if not use_cached:
        kalshi_data.fetch_kalshi_data_with_priorities()
        polymarket_data.fetch_prices(max_days=MAX_DAYS_TO_RESOLUTION)
        polymarket_data.fetch_macro_events()
        polymarket_data.fetch_priority_searches()
        polymarket_data.supplement_from_kalshi_searches(
            kalshi_data.get_raw_kalshi_markets(),
        )
    polymarket_data.extract_polymarket_details()
    kalshi_data.extract_kalshi_details()


def discover_current_opportunities():
    matching.matched_markets.clear()
    match_result = matching.match_all_markets(
        polymarket_data.clean_markets_polymarket,
        kalshi_data.clean_markets_kalshi,
        quiet=True,
    )
    scan = math_engine.scan_all_opportunities(match_result["pairs"])
    return (
        scan["internal_polymarket"]
        + scan["internal_kalshi"]
        + scan["cross_platform"]
    )


def run_logger(cycles=None, interval=SNAPSHOT_INTERVAL_SECONDS, max_tracking_minutes=30, use_cached=False):
    logger = ArbitrageLogger(
        snapshot_interval_seconds=interval,
        max_tracking_seconds=max_tracking_minutes * 60,
    )
    cycle = 0

    print(f"Logging session file: {logger.session_file}")
    print(f"CSV file: {logger.csv_file}")
    print(
        f"Snapshot interval: {interval}s | Max tracking: {max_tracking_minutes}m | "
        f"Horizon: {MAX_DAYS_TO_RESOLUTION} days"
    )
    print("Press Ctrl+C to stop.\n")

    try:
        while cycles is None or cycle < cycles:
            cycle += 1
            print(f"=== Cycle {cycle} | {utc_now_iso()} ===")
            refresh_market_data(use_cached=use_cached)
            discovered = discover_current_opportunities()
            logger.register_discoveries(discovered)

            lookup = build_market_lookup()
            logger.update_snapshots(lookup)
            logger.save()
            print(
                f"Active trackers: {len(logger.active_trackers)} | "
                f"Total logged opportunities: {len(logger.session_data['opportunities'])}\n"
            )

            if cycles is None or cycle < cycles:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopping logger...")
        logger.save()
        print(f"Saved session to {logger.session_file}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Log arbitrage opportunities and track them every 30 seconds."
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Number of refresh cycles to run. Default: run until Ctrl+C.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=SNAPSHOT_INTERVAL_SECONDS,
        help="Seconds between refresh/snapshot cycles.",
    )
    parser.add_argument(
        "--max-tracking-minutes",
        type=int,
        default=30,
        help="Stop tracking an opportunity after this many minutes.",
    )
    parser.add_argument(
        "--use-cached",
        action="store_true",
        help="Use existing JSON files instead of re-fetching from APIs.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_logger(
        cycles=args.cycles,
        interval=args.interval,
        max_tracking_minutes=args.max_tracking_minutes,
        use_cached=args.use_cached,
    )
