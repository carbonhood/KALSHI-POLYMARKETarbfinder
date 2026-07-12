# IBKR Client Portal Gateway — ForecastEx setup

The scanner can pull **ForecastEx** prices through Interactive Brokers' local API gateway.
This requires **your** IBKR account — the agent cannot log in or run this autonomously on your behalf.

## Why it can't be fully automated

1. **IBKR login + 2FA** — you must authenticate in a browser or mobile app.
2. **Local Java process** — gateway runs on your machine, not in this repo.
3. **Account permissions** — ForecastTrader / event contracts must be enabled on your account.
4. **Security** — credentials never belong in code or git.

## Setup (one-time)

### 1. IBKR account

- Open or use an existing [Interactive Brokers](https://www.interactivebrokers.com/) account.
- Enable **ForecastTrader** / event contracts in account settings if prompted.

### 2. Download Client Portal Gateway

- Download from IBKR: [Client Portal API](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/)
- Or search IBKR docs for **"Client Portal Gateway"** (Java `.zip`).

Typical layout after extract:

```
clientportal.gw/
  bin/run.bat          # Windows
  bin/run.sh           # Mac/Linux
  root/conf.yaml
```

### 3. Start the gateway

**Windows (PowerShell):**

```powershell
cd path\to\clientportal.gw
.\bin\run.bat root\conf.yaml
```

**Mac/Linux:**

```bash
cd path/to/clientportal.gw
./bin/run.sh root/conf.yaml
```

### 4. Log in

1. Open **https://localhost:5000** in your browser.
2. Accept the self-signed certificate warning.
3. Log in with IBKR username/password + 2FA.
4. Leave the gateway running while scanning.

### 5. Configure this project

In `.env`:

```
IBKR_GATEWAY_URL=https://localhost:5000/v1/api
```

In `config.py`:

```python
FORECASTEX_USE_IBKR_GATEWAY = True
SCAN_FORECASTEX = True
```

### 6. Run the scanner

```bash
python main.py
```

Or test gateway connectivity:

```bash
python -c "from forecastex_data import fetch_from_ibkr_gateway; fetch_from_ibkr_gateway()"
```

## Manual alternative (no gateway)

Export markets from [ForecastTrader](https://forecasttrader.interactivebrokers.com/) and save as `forecastex_data.json` using `forecastex_data.example.json` as a template.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Connection refused on :5000 | Gateway not running — start `run.bat` |
| 401 / not authenticated | Re-login at https://localhost:5000 |
| SSL certificate error | Expected for localhost; proceed in browser |
| Empty ForecastEx markets | Search symbols may need adjustment in `forecastex_data.py` |
| Session timeout | Gateway needs periodic `/tickle` — scanner calls this when gateway mode is on |

## Security notes

- Do not commit `.env` or IBKR credentials.
- Gateway exposes a local API — only run on trusted machines.
- Read-only market data is lower risk than enabling order placement.
