# Netlify + GitHub Actions — live dashboard while you're away

Scans run in the cloud every **15 minutes**. Netlify hosts a phone-friendly dashboard that reads results from GitHub.

## Quick start

1. **Push** `version-1.2` to GitHub
2. **Merge to `main`** (or set `version-1.2` as default branch) — scheduled cron only runs on the default branch
3. **Actions** → **Scheduled Arb Scan** → **Run workflow** (wait 5–10 min)
4. **Netlify** → import repo, branch `version-1.2`, publish dir `web/netlify` (see `netlify.toml`)
5. Open Netlify URL on your phone

Full details below.

## Architecture

```
GitHub Actions (every 15 min, UTC)
  → full Kalshi/Polymarket scan
  → publishes JSON to `scan-data` branch

Netlify (static)
  → fetches JSON from raw.githubusercontent.com/.../scan-data/
  → auto-refresh every 60 seconds
```

## Setup

### 1. Push to GitHub

```bash
git push -u origin version-1.2
```

**Repo must be public** (or at least the `scan-data` branch readable) so Netlify can load JSON without a token.

### 2. Default branch for scheduled scans

GitHub only runs `schedule` cron on the **default branch**. Either:

- Merge `version-1.2` into `main`, or
- Settings → General → Default branch → `version-1.2`

### 3. Run first scan manually

1. Repo → **Actions** → **Scheduled Arb Scan**
2. **Run workflow** → pick branch with the workflow file
3. Wait for green checkmark (~5–10 min)

Verify data exists:

```
https://raw.githubusercontent.com/carbonhood/KALSHI-POLYMARKETarbfinder/scan-data/macro_arb_latest.json
```

(Change `bardl` / repo name if needed.)

### 4. Deploy to Netlify

1. [app.netlify.com](https://app.netlify.com) → **Add new site** → **Import from Git**
2. Repo: `KALSHI-POLYMARKETarbfinder`, branch: `version-1.2`
3. `netlify.toml` sets publish directory to `web/netlify`
4. Deploy

Edit `web/netlify/js/config.js` if GitHub user/repo differs, then redeploy.

## Files on `scan-data` branch

| File | Purpose |
|------|---------|
| `macro_arb_latest.json` | Latest opportunities + watchlist |
| `scan_meta.json` | Last scan time, errors |
| `scan_history.json` | Rolling log (dashboard shows today's rows) |
| `config_snapshot.json` | Active scanner config |

## While you're out today

1. Trigger one manual scan before you leave
2. Open Netlify URL on phone — refreshes every 60s
3. **Today's Scan Log** shows each run from today (UTC)
4. Scans continue every 15 min automatically

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No data on dashboard | Run workflow manually; confirm `scan-data` branch exists |
| 404 on raw JSON | Public repo required; check user/repo in `config.js` |
| Cron not running | Workflow must be on **default branch** |
| Workflow fails | Check Actions log (API rate limits, timeouts) |

## Local dashboard (optional)

```bash
python -m web.server
```

Netlify site is read-only; scans run only via GitHub Actions.
