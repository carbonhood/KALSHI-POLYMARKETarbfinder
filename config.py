# Shared settings for the macro arbitrage pipeline.

# --- Horizon ---
MACRO_MAX_DAYS_TO_RESOLUTION = 45
POLITICS_MAX_DAYS_TO_RESOLUTION = 150  # Senate/House races resolve on election day
GEOPOLITICS_MAX_DAYS_TO_RESOLUTION = 90
SPORTS_PM_MAX_DAYS_TO_RESOLUTION = 14
CRYPTO_MAX_DAYS_TO_RESOLUTION = 90
LEGAL_MAX_DAYS_TO_RESOLUTION = 120
MAX_DAYS_TO_RESOLUTION = 7  # legacy log_arbitrage.py default

# --- API limits ---
KALSHI_MAX_MARKETS = 7500
POLYMARKET_MAX_EVENTS = 1500
MACRO_POLYMARKET_MAX_EVENTS = 1500
KALSHI_PAGE_LIMIT = 200
POLYMARKET_PAGE_LIMIT = 100
POLYMARKET_CLOB_BATCH_SIZE = 500
KALSHI_POLY_SEARCH_LIMIT = 120

# Kalshi API pacing (avoid 429 rate limits on bulk + politics supplements)
KALSHI_REQUEST_MAX_RETRIES = 8
KALSHI_PAGE_DELAY_SECONDS = 0.25
KALSHI_SERIES_DELAY_SECONDS = 0.35
KALSHI_POLITICS_SERIES_DELAY_SECONDS = 0.5
KALSHI_USE_CACHED_ON_RATE_LIMIT = True

# --- Category toggles ---
# Tier 1: macro, politics_elections, geopolitics
# Tier 2: sports_pm, crypto, legal
ENABLED_CATEGORIES = (
    "macro",
    "politics_elections",
    "geopolitics",
    "sports_pm",
    "crypto",
    "legal",
)


def scan_horizon_days():
    """Widest fetch/extract window across enabled categories."""
    horizon_map = {
        "macro": MACRO_MAX_DAYS_TO_RESOLUTION,
        "politics_elections": POLITICS_MAX_DAYS_TO_RESOLUTION,
        "geopolitics": GEOPOLITICS_MAX_DAYS_TO_RESOLUTION,
        "sports_pm": SPORTS_PM_MAX_DAYS_TO_RESOLUTION,
        "crypto": CRYPTO_MAX_DAYS_TO_RESOLUTION,
        "legal": LEGAL_MAX_DAYS_TO_RESOLUTION,
    }
    horizons = [horizon_map[c] for c in ENABLED_CATEGORIES if c in horizon_map]
    return max(horizons or [MACRO_MAX_DAYS_TO_RESOLUTION])

# Per-category max capital lock (days).
MAX_HOLD_DAYS_BY_CATEGORY = {
    "macro": 45,
    "politics_elections": 150,
    "geopolitics": 90,
    "sports_pm": 7,
    "crypto": 90,
    "legal": 120,
}

# --- Polymarket discovery by category ---
MACRO_POLYMARKET_TAGS = (
    "finance",
    "economics",
    "fed-rates",
    "fed",
)

POLITICS_POLYMARKET_TAGS = (
    "politics",
    "us-politics",
    "elections",
)

GEOPOLITICS_POLYMARKET_TAGS = (
    "geopolitics",
    "world",
)

SPORTS_PM_POLYMARKET_TAGS = (
    "sports",
    "nfl",
    "nba",
    "mlb",
)

CRYPTO_POLYMARKET_TAGS = (
    "crypto",
    "bitcoin",
)

LEGAL_POLYMARKET_TAGS = (
    "politics",
    "court",
)

MACRO_POLYMARKET_SEARCHES = (
    "Federal Reserve FOMC",
    "CPI inflation",
    "unemployment rate",
    "Bank of Korea",
    "Bank of Japan",
    "ECB rate",
    "Bank of England",
    "nonfarm payroll",
    "GDP",
    "RBA rate",
)

POLITICS_POLYMARKET_SEARCHES = (
    "Senate race 2026",
    "Republicans win Senate",
    "Democrats win Senate",
    "House race 2026",
    "Republicans win House",
    "Democrats win House",
    "gubernatorial 2026",
    "Governor Republican primary",
    "control of the Senate",
    "control of the House",
)

GEOPOLITICS_POLYMARKET_SEARCHES = (
    "Putin Zelenskyy meet",
    "Trump recognize",
    "ceasefire",
    "tariff",
    "sanctions",
)

SPORTS_PM_POLYMARKET_SEARCHES = (
    "NFL winner",
    "NBA winner",
    "MLB winner",
    "Super Bowl",
)

CRYPTO_POLYMARKET_SEARCHES = (
    "Bitcoin above",
    "Ethereum above",
    "BTC price",
    "ETH price",
)

LEGAL_POLYMARKET_SEARCHES = (
    "convicted",
    "indicted",
    "sentenced",
)

# Kalshi series supplements by overlap quality.
KALSHI_MACRO_PRIORITY_SERIES = (
    "KXECONSTATU3",
    "KXPAYROLLS",
    "KXU3",
    "KXFEDDECISION",
    "KXCPI",
    "KXGDPCN",
)

KALSHI_POLITICS_PRIORITY_SERIES = (
    "SENATE",
    "HOUSE",
    "GOV",
)

KALSHI_SPORTS_PM_PRIORITY_SERIES = (
    "KXNFL",
    "KXNBA",
    "KXMLB",
    "KXNHL",
)

KALSHI_CRYPTO_PRIORITY_SERIES = (
    "KXBTC",
    "KXETH",
)

KALSHI_PRIORITY_SERIES = (
    KALSHI_MACRO_PRIORITY_SERIES
    + KALSHI_POLITICS_PRIORITY_SERIES
    + KALSHI_SPORTS_PM_PRIORITY_SERIES
    + KALSHI_CRYPTO_PRIORITY_SERIES
)

POLYMARKET_PRIORITY_SEARCHES = MACRO_POLYMARKET_SEARCHES

# --- Matching ---
MIN_MATCH_CONFIDENCE = 0.85
MATCH_CONFIDENCE = {
    "crosswalk": 1.0,
    "event_cluster_equivalent_outcome": 0.95,
    "llm_cache_equivalent_outcome": 0.88,
    "entity_matchup_outcome": 0.92,
    "entity_threshold_subject": 0.90,
    "high_similarity": 0.80,
    "keyword_similarity": 0.75,
}
CROSSWALK_PATH = "crosswalk.json"

# --- LLM extraction cache (v1.3) ---
# Scans read cache only (no API calls). Populate on demand via scripts/enrich_market_cache.py
LLM_CACHE_ENABLED = True
LLM_CACHE_PATH = "llm_extraction_cache.sqlite"
LLM_MIN_CONFIDENCE = 0.85
LLM_MODEL = "gpt-4o-mini"
LLM_API_BASE = "https://api.openai.com/v1"
LLM_MAX_RETRIES = 3
LLM_REQUEST_TIMEOUT_SECONDS = 60
LLM_REQUEST_DELAY_SECONDS = 0.25
LLM_MATCH_METHOD = "llm_cache"

# --- Arb filters (research mode) ---
MIN_MACRO_PROFIT = 0.003
MIN_MACRO_ANNUALIZED_RETURN = 0.05
MAX_MACRO_HOLD_DAYS = 45
EXCLUDE_LONG_DATED_POLITICS = False

# --- Book quality (YES + NO ask sum must fall in this range) ---
MIN_BINARY_BOOK_SUM = 0.88
MAX_BINARY_BOOK_SUM = 1.12

# --- Liquidity / fillability ---
MIN_FILLABLE_CONTRACTS = 5  # 0 = disabled
MIN_VOLUME_24H = 0  # 0 = disabled
ENRICH_LIQUIDITY_ON_SCAN = True
POLYMARKET_CLOB_BOOK_BATCH_SIZE = 100

# --- Venues ---
SCAN_KALSHI = True
SCAN_POLYMARKET = True
SCAN_FORECASTEX = True
FORECASTEX_USE_IBKR_GATEWAY = False

# --- Sportsbooks (parked — see SPORTS_ARB.md) ---
SCAN_CROSS_BOOK_ARBS = False
SCAN_KALSHI_VS_BOOKS = False
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_REGIONS = "uk,eu,us,au"
ODDS_API_MARKETS = "h2h"
ODDS_API_ODDS_FORMAT = "decimal"
MAX_SPORTS_TO_SCAN = 10
SPORTS_PRIORITY_KEYS = ()
MIN_SPORTS_ARB_PROFIT = 0.005
DEFAULT_BOOK_COMMISSION = 0.02
BOOKMAKER_COMMISSIONS = {}

# --- Web control center ---
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080
