# Macro Event Arbitrage Finder

Automated cross-venue arbitrage scanner for **macro/finance prediction markets** on:

- **Kalshi** (CFTC-regulated)
- **Polymarket** (CLOB best-ask pricing)
- **ForecastEx** (via IBKR / manual cache)

Opportunities are ranked by **annualized return** (profit / hold days × confidence).

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

Use cached data (skip API fetches):

```bash
python main.py --cached
```

### Web control center (v1.3)

Start the dashboard (phone-friendly, same machine or LAN):

```bash
pip install -r requirements.txt
python -m web.server
```

Open `http://localhost:8080` (or your host IP on port 8080 from your phone on the same network).

- **Quick Scan** — uses cached Kalshi/Polymarket JSON
- **Full Scan** — fetches fresh data from APIs
- **LLM cache enrich** — on-demand API populate (`POST /api/enrich-cache`); scans read cache only
- View opportunities, watchlist pairs, and live config

See **[LLM_EXTRACTION.md](LLM_EXTRACTION.md)** for the v1.3 LLM cache workflow.

### Netlify dashboard (log while away)

For cloud scans every 15 minutes + phone dashboard without your PC on:

See **[NETLIFY_DEPLOY.md](NETLIFY_DEPLOY.md)** — GitHub Actions publishes to `scan-data` branch; Netlify hosts the read-only dashboard.

Results: `macro_arb_results.json` (includes `matched_pair_summaries` for research)

## Monitoring (research phase)

```bash
# Macro cross-venue monitor (recommended)
python log_macro_arb.py --interval 120 --cycles 10

# Legacy Poly×Kalshi tracker with 30s price snapshots
python log_arbitrage.py --interval 30 --cycles 5
```

## How matching works

Markets are paired in priority order:

1. **Event clusters** — canonical `event_key` + equivalent `canonical_outcome` (Fed, CPI buckets, unemployment, etc.)
2. **LLM cache (v1.3)** — cached structured extractions for markets regex parsers miss (geopolitics, legal, title drift)
3. **Crosswalk** — manual high-confidence mappings in `crosswalk.json`
4. **Title/entity fuzzy match** — Polymarket × Kalshi fallback (confidence ≥ 0.85)

Supported event types: central bank decisions, CPI/NFP/unemployment releases, **Senate/House/governor races**, chamber control, geopolitics, **crypto thresholds**, **sports PM game winners**, **legal outcomes** (title/event_key match).

**v1.2 categories (Tier 1 + Tier 2):** `macro`, `politics_elections`, `geopolitics`, `sports_pm`, `crypto`, `legal`. API limits: Kalshi **7500** markets, Polymarket **1500** events.

Politics markets use a **150-day fetch horizon** and per-state Kalshi series (`SENATEID`, `SENATEIA`, etc.). See `politics_normalization.py`.

## ForecastEx

Beginner setup guide: **[FORECASTEX_SETUP.md](FORECASTEX_SETUP.md)**

## Configuration (`config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `MACRO_MAX_DAYS_TO_RESOLUTION` | 45 | Fetch horizon |
| `MAX_MACRO_HOLD_DAYS` | 45 | Skip long-dated locks |
| `MIN_MACRO_PROFIT` | 0.5% | Min edge per $1 payout |
| `MIN_MACRO_ANNUALIZED_RETURN` | 15% | Min profit/hold annualized |
| `MIN_MATCH_CONFIDENCE` | 0.85 | Min confidence to accept a pair |
| `SCAN_FORECASTEX` | True | Include ForecastEx venue |
| `FORECASTEX_USE_IBKR_GATEWAY` | False | Live IBKR fetch |

### Research mode (more results, lower bar)

```python
MIN_MACRO_ANNUALIZED_RETURN = 0.05
MIN_MACRO_PROFIT = 0.003
MIN_MATCH_CONFIDENCE = 0.75
```

## ForecastEx setup

1. **Manual cache** — export markets to `forecastex_data.json` (see `forecastex_data.example.json`)
2. **IBKR Gateway** — set in `.env`:
   ```
   IBKR_GATEWAY_URL=http://localhost:5000/v1/api
   FORECASTEX_USE_IBKR_GATEWAY=True
   ```

## Extending matches

Add entries to `crosswalk.json` for events that share resolution rules but differ in title format. Example structure:

```json
{
  "id": "bank_of_korea_july_2026",
  "event_key": ["central_bank", "bank_of_korea", 2026, 7],
  "outcome_groups": [
    {"kalshi": ["hold"], "polymarket": ["hold"]},
    {"kalshi": ["hike_small", "hike"], "polymarket": ["hike"]}
  ]
}
```

## Sports arb (parked)

See `SPORTS_ARB.md` for the sports prediction-market path.

## Research phase workflow

1. Run `python main.py` daily around macro releases (FOMC, CPI, NFP, unemployment)
2. Review `matched_pair_summaries` in results even when no arb exists
3. Extend `crosswalk.json` for high-confidence event mappings
4. Use `log_macro_arb.py` to track price dislocations over time
5. Verify resolution rules before trading any opportunity
