# LLM Market Extraction (v1.3)

Structured market metadata from an LLM, with **cache-only scans** and **on-demand population**.

## Architecture

1. **On demand:** `scripts/enrich_market_cache.py` (or `POST /api/enrich-cache`) calls OpenAI for markets regex parsers miss.
2. **Every scan:** `attach_event_metadata()` reads `llm_extraction_cache.sqlite` only — **no LLM API calls**.
3. **Safety:** Regex parsers win when they produce an `event_key`. LLM fills gaps only.

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
```

Optional `.env` (see `.env.example`).

## Populate cache (costs API credits)

```bash
# Use cached venue JSON, enrich up to 50 gap markets (default limit in web UI)
python scripts/enrich_market_cache.py --cached --limit 50

# Preview candidates without calling the API
python scripts/enrich_market_cache.py --cached --dry-run

# Re-extract everything (expensive)
python scripts/enrich_market_cache.py --cached --all --force
```

## Scan (free — cache read only)

```bash
python main.py --cached
```

Scan output includes `llm_cache_usage` and `llm_cache_store` stats.

## Web control center

```bash
python -m web.server
```

- `GET /api/llm-cache` — cache stats
- `POST /api/enrich-cache` — background enrichment (`{"cached": true, "limit": 50}`)

## Config (`config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `LLM_CACHE_ENABLED` | `True` | Read cache during scans |
| `LLM_CACHE_PATH` | `llm_extraction_cache.sqlite` | SQLite store |
| `LLM_MIN_CONFIDENCE` | `0.85` | Min extraction confidence |
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI model |
| `LLM_MATCH_METHOD` | `llm_cache` | `metadata_source` tag |

## Matching behavior

- LLM-derived pairs use `match_method: llm_cache_equivalent_outcome` with confidence from the extraction (capped by `MATCH_CONFIDENCE`).
- `resolution_risk_flags` on markets surface aggregate-vs-sized-bucket and similar risks.
- Geopolitics/legal markets can cluster via `event_type: geopolitical` when cached.

## Files

| File | Role |
|------|------|
| `schemas/canonical_market.json` | Extraction JSON schema |
| `llm_extraction.py` | OpenAI client + enrich batch |
| `llm_extraction_cache.py` | SQLite cache |
| `llm_market_payload.py` | Venue payload + cache keys |
| `llm_prompts.py` | System/user prompts |
| `canonical_derive.py` | canonical JSON → `event_key` |
| `extraction_validator.py` | Schema + safety validation |
| `scripts/enrich_market_cache.py` | CLI enrichment |

## GitHub Actions

Scheduled scans do **not** call the LLM. Run enrichment locally (or a separate manual workflow) and commit `llm_extraction_cache.sqlite` if you want cloud scans to use it — otherwise cloud scans rely on regex parsers only.
