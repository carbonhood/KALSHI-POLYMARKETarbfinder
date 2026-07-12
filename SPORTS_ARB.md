# Sports Prediction-Market Arbitrage (Parked)

This branch of work is **on hold** while the project focuses on **macro event arbitrage**
(Kalshi, Polymarket, ForecastEx). Return here when ready to implement sports PM arbs.

## Scope (prediction markets only)

Not traditional sportsbook line-shopping (DraftKings -110 vs FanDuel +105). Target **event contracts**:

| Venue | Type |
|-------|------|
| Kalshi | CFTC sports event contracts |
| DraftKings Predictions | CFTC event contracts |
| FanDuel Predicts | CFTC / CME-backed event contracts |
| Novig, OG (Crypto.com) | CFTC sports P2P |

## Existing code (ready to wire)

| File | Purpose |
|------|---------|
| `sports_odds.py` | The Odds API client (traditional books — **optional**, not PM-only) |
| `sports_arb.py` | Cross-book surebets + Kalshi-vs-books engines |
| `sports_team_match.py` | Team name normalization |
| `log_sports_arb.py` | Interval polling logger |

## Recommended sports PM path (when resumed)

1. **Disable** `SCAN_CROSS_BOOK_ARBS` (traditional books) unless explicitly wanted.
2. **Enable** Kalshi ↔ DraftKings/FanDuel Predictions matching (same game, same contract).
3. Filter to **game-winner** markets with hold **< 72 hours**.
4. Rank by **annualized return** = `(edge / hold_hours) × 8760`.
5. Require minimum size at quoted ask on both legs.

## Expected performance (estimates)

| Metric | Sports PM |
|--------|-----------|
| Avg capital lock | 1–2 days |
| Fillable trades/year (active) | 50–150 |
| Typical edge | 0.8–2.5% |
| Likely annual return | ~5–12% on bankroll |

## API gaps

- DraftKings Predictions / FanDuel Predicts: **no public trading API** today.
- Kalshi + Polymarket: public APIs (already integrated in macro pipeline).
- Novig: early; API TBD.

## To resume

```bash
# Restore sports-first main (see git history) or add toggle in config:
# SCAN_MODE = "sports"
python log_sports_arb.py --interval 60
```

See conversation notes on sportsbook TOS vs prediction-market TOS before enabling cross-book Odds API scanning.
