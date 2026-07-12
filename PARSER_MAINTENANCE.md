# Parser Maintenance Guide

Use this document when Kalshi or Polymarket change titles, tickers, bucket formats, or API fields and matching quality drops.

## Cursor prompt (copy everything below the line)

---

You are the lead engineer on this Kalshi × Polymarket × ForecastEx arbitrage repo (branch `version-1.2`).

### Goal
Update the market parsers / normalizers so cross-venue matching keeps working after platform title, ticker, or API format changes. Do NOT rewrite the whole pipeline. Fix parsers, category filters, and crosswalk entries only.

### Architecture (do not break)
- Entry: `main.py` → `macro_pipeline.py` → `macro_arb.py`
- Web control center: `web/server.py` (optional — do not break API routes)
- Matching priority:
  1. Event clusters via `event_key` + `canonical_outcome`
  2. Manual `crosswalk.json`
  3. Title/entity fuzzy match (`matching.py`, Poly×Kalshi only)
- Normalization lives in:
  - `outcome_normalization.py` (macro: Fed, CPI, NFP, unemployment, buckets)
  - `politics_normalization.py` (Senate/House/governor/chamber control)
  - `crypto_normalization.py` (BTC/ETH price thresholds)
  - `sports_pm_normalization.py` (game-winner sports PM)
  - `legal_normalization.py` (court / conviction outcomes)
  - `entity_matching.py` (matchups / thresholds)
  - `market_categories.py` (category + hold-day filters)
- Fetch: `kalshi_data.py`, `polymarket_data.py`, `forecastex_data.py`
- Config: `config.py` (horizons, categories, confidence, research filters)
- Logging: keep `log_macro_arb.py` / research outputs intact
- ForecastEx: manual `forecastex_data.json` only for now (IBKR gateway parked)

### What to do
1. Fetch fresh data (or use `--cached` if I say so), then diagnose:
   - Markets that SHOULD match but have `event_key=None` or mismatched keys/outcomes
   - Category filter dropping valid markets
   - Horizon / far-future politics close dates incorrectly excluding Senate/House
2. Update parsers for broken formats (titles, `yes_sub_title`, `group_item_title`, tickers like `SENATEID-26-R`).
3. Add/adjust `crosswalk.json` only for high-confidence same-resolution mappings.
4. Extend categories only when both venues have real overlap.
5. Verify with `python main.py` (or `--cached`) and report:
   - matched pair count before/after
   - sample matched pairs by category
   - any remaining known gaps

### Constraints
- Prefer structured `event_key` matching over lowering fuzzy thresholds
- Never treat aggregate outcomes (e.g. Poly “hike”) as equivalent to sized buckets (e.g. Kalshi “hike_small”) unless crosswalk explicitly maps them and you flag resolution risk
- Do not commit unless I ask
- Do not remove the logging system
- Keep changes minimal and focused on matching quality

### Context for this session
[PASTE WHAT BROKE — examples:]
- “Senate races stopped matching after Kalshi renamed titles”
- “CPI Core MoM buckets no longer get event_keys”
- “Polymarket unemployment titles changed from ‘be 4.0%’ to ‘exactly 4.0%’”
- “Add House race matching like Senate”
- Paste 2–5 example market titles/tickers from each platform that should match

### Success criteria
More correct high-confidence matched pairs, zero obvious false matches in the top results, and a short summary of parser changes + remaining gaps.

---

## Quick diagnostic commands

```bash
python main.py --cached
python -m web.server
```

Check `macro_arb_results.json` → `matched_pair_summaries` and `opportunity_count`.

## Files most likely to need edits

| Symptom | Start here |
|---------|------------|
| Macro buckets (CPI, NFP, Fed) | `outcome_normalization.py` |
| Senate / House / governor | `politics_normalization.py` |
| Sports game winners | `sports_pm_normalization.py` |
| BTC / ETH thresholds | `crypto_normalization.py` |
| Court / legal outcomes | `legal_normalization.py` |
| Market filtered out wrongly | `market_categories.py` |
| Kalshi not fetched | `kalshi_data.py`, `config.py` |
| Manual override | `crosswalk.json` |
