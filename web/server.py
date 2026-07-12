# FastAPI web control center — run with: python -m web.server
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    ENABLED_CATEGORIES,
    ENRICH_LIQUIDITY_ON_SCAN,
    FORECASTEX_USE_IBKR_GATEWAY,
    KALSHI_MAX_MARKETS,
    MACRO_MAX_DAYS_TO_RESOLUTION,
    MAX_HOLD_DAYS_BY_CATEGORY,
    MAX_MACRO_HOLD_DAYS,
    MIN_FILLABLE_CONTRACTS,
    MIN_MACRO_ANNUALIZED_RETURN,
    MIN_MACRO_PROFIT,
    MIN_VOLUME_24H,
    POLITICS_MAX_DAYS_TO_RESOLUTION,
    POLYMARKET_MAX_EVENTS,
    SCAN_FORECASTEX,
    SCAN_KALSHI,
    SCAN_POLYMARKET,
    WEB_HOST,
    WEB_PORT,
    scan_horizon_days,
)
from macro_pipeline import run_macro_scan, save_macro_results

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
RESULTS_PATH = Path("macro_arb_results.json")

app = FastAPI(title="Arb Finder Control Center", version="1.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_scan_lock = threading.Lock()
_scan_state = {
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_error": None,
    "use_cached": False,
}


class ScanRequest(BaseModel):
    cached: bool = False


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load_saved_results():
    if not RESULTS_PATH.exists():
        return None
    with open(RESULTS_PATH, encoding="utf-8") as file:
        return json.load(file)


def _config_snapshot():
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
        "liquidity": {
            "enrich_on_scan": ENRICH_LIQUIDITY_ON_SCAN,
            "min_fillable_contracts": MIN_FILLABLE_CONTRACTS,
            "min_volume_24h": MIN_VOLUME_24H,
        },
    }


def _run_scan_background(cached: bool):
    global _scan_state
    with _scan_lock:
        if _scan_state["running"]:
            return
        _scan_state["running"] = True
        _scan_state["last_started"] = _utc_now_iso()
        _scan_state["last_error"] = None
        _scan_state["use_cached"] = cached

    try:
        result = run_macro_scan(quiet=True, use_cached=cached)
        save_macro_results(result, path=str(RESULTS_PATH))
        with _scan_lock:
            _scan_state["last_finished"] = _utc_now_iso()
    except Exception as exc:
        with _scan_lock:
            _scan_state["last_error"] = str(exc)
            _scan_state["last_finished"] = _utc_now_iso()
    finally:
        with _scan_lock:
            _scan_state["running"] = False


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status():
    results = _load_saved_results()
    return {
        "scan": dict(_scan_state),
        "results_available": results is not None,
        "summary": {
            "opportunity_count": results.get("opportunity_count", 0) if results else 0,
            "matched_pairs": results.get("matched_pairs", 0) if results else 0,
            "market_counts": results.get("macro_market_counts", {}) if results else {},
            "kalshi_funnel": results.get("kalshi_funnel", {}) if results else {},
        },
        "config": _config_snapshot(),
    }


@app.get("/api/config")
def config():
    return _config_snapshot()


@app.get("/api/results")
def results():
    data = _load_saved_results()
    if not data:
        raise HTTPException(status_code=404, detail="No scan results yet. Run a scan first.")
    return data


@app.post("/api/scan")
def start_scan(request: ScanRequest):
    with _scan_lock:
        if _scan_state["running"]:
            raise HTTPException(status_code=409, detail="Scan already in progress")

    thread = threading.Thread(target=_run_scan_background, args=(request.cached,), daemon=True)
    thread.start()
    mode = "cached" if request.cached else "fresh"
    return {"ok": True, "message": f"Scan started ({mode} data)", "started_at": _utc_now_iso()}


def main():
    import uvicorn

    uvicorn.run("web.server:app", host=WEB_HOST, port=WEB_PORT, reload=False)


if __name__ == "__main__":
    main()
