# ForecastEx Setup — Beginner Guide

ForecastEx is the third venue in this scanner. Unlike Kalshi and Polymarket (which have public APIs), ForecastEx data usually comes through **Interactive Brokers (IBKR)** or a **manual JSON file** you maintain.

## What you need

1. An Interactive Brokers account with ForecastEx / ForecastTrader access, **or**
2. Manually copied market prices from the ForecastEx website

## Option A: Manual cache (easiest to start)

This is the best way to learn the format without setting up IBKR.

### Step 1 — Create the data file

Copy the example file:

```bash
copy forecastex_data.example.json forecastex_data.json
```

On Mac/Linux:

```bash
cp forecastex_data.example.json forecastex_data.json
```

### Step 2 — Add real markets

Open `forecastex_data.json` in any text editor. Each market needs:

| Field | What it means | Example |
|-------|---------------|---------|
| `market_question` | The exact question text | `"Will the Fed lower the target rate at the July 2026 meeting?"` |
| `yes_price` | Cost to buy YES (0–1) | `0.42` |
| `no_price` | Cost to buy NO (0–1) | `0.59` |
| `end_date` | When it resolves (ISO date) | `"2026-07-30T20:00:00Z"` |
| `event_title` | Optional grouping label | `"Fed Funds Target Rate July 2026"` |
| `conid` | Optional IBKR contract ID | `"12345678"` |

Example with two markets:

```json
{
  "source": "manual_export",
  "markets": [
    {
      "market_question": "Will the Fed lower the target rate at the July 2026 meeting?",
      "yes_price": 0.42,
      "no_price": 0.59,
      "end_date": "2026-07-30T20:00:00Z",
      "event_title": "Fed Funds Target Rate July 2026",
      "conid": "manual_fed_july_2026"
    },
    {
      "market_question": "Will July 2026 CPI YoY be at or above 3.0%?",
      "yes_price": 0.35,
      "no_price": 0.67,
      "end_date": "2026-08-12T14:00:00Z",
      "event_title": "CPI YoY July 2026"
    }
  ]
}
```

### Step 3 — Where to get prices

1. Log into ForecastEx / ForecastTrader
2. Find a market that also exists on Kalshi or Polymarket
3. Copy the **best ask** (or mid) prices for YES and NO
4. Paste into `forecastex_data.json`

**Important:** Only add markets that mean the **same thing** as a Kalshi/Polymarket market. Resolution rules must match or the arb is fake.

### Step 4 — Run the scanner

In `config.py`, confirm:

```python
SCAN_FORECASTEX = True
FORECASTEX_USE_IBKR_GATEWAY = False
```

Then run:

```bash
python main.py
```

ForecastEx markets are matched by **event key** (same as macro events). If titles parse into the same `event_key` and `canonical_outcome`, they pair automatically.

### Step 5 — Refresh prices

Manual cache does **not** auto-update. Before each scan session:

1. Update `yes_price` / `no_price` in `forecastex_data.json`
2. Run `python main.py` again

For research, update prices daily around macro releases.

---

## Option B: IBKR Gateway (automated)

Use this when you want live ForecastEx prices without hand-editing JSON.

### Step 1 — Install IBKR Gateway

1. Download **IBKR Gateway** (not TWS) from Interactive Brokers
2. Install and log in with your IB credentials
3. Enable **API access** in Gateway settings

See `IBKR_GATEWAY.md` in this repo for port and SSL details.

### Step 2 — Configure environment

Create a `.env` file in the project root (copy from `.env.example`):

```
IBKR_GATEWAY_URL=http://localhost:5000/v1/api
FORECASTEX_USE_IBKR_GATEWAY=True
```

### Step 3 — Enable in config

```python
SCAN_FORECASTEX = True
FORECASTEX_USE_IBKR_GATEWAY = True
```

### Step 4 — Start Gateway, then scan

1. Start IBKR Gateway and log in
2. Run `python main.py`

The scanner calls `forecastex_data.fetch_from_ibkr_gateway()` to pull open contracts.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `forecastex_macro: 0` markets | Create `forecastex_data.json` or enable IBKR gateway |
| No ForecastEx pairs matched | Titles must parse to same `event_key` — align wording with Kalshi/Poly |
| Gateway connection error | Check Gateway is running, URL matches `.env`, API enabled |
| Fake arb on ForecastEx | ForecastEx adds ~1% spread premium in fee math — verify manually |

---

## Tips for good ForecastEx entries

1. **Start with Fed and CPI** — same events already matching on Kalshi × Polymarket
2. **Match the outcome bucket** — "cut 25bps" must pair with "cut 25bps", not "any cut"
3. **Use `event_title`** — helps the parser find month/year when the question is short
4. **Keep `conid` unique** — avoids dedup collisions if you add many markets

---

## Next step after setup

Run the monitor to watch ForecastEx legs over time:

```bash
python log_macro_arb.py --interval 120 --cycles 20
```

Check `logs/macro_arb_latest.json` for matched pairs that include `ForecastEx` as a platform.
