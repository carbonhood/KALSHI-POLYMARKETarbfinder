# LLM cache usage stats during scans (read-only; no API calls).
from config import LLM_CACHE_ENABLED, LLM_MATCH_METHOD


def summarize_llm_cache_usage(markets):
    """Count metadata sources across a market list."""
    stats = {
        "enabled": LLM_CACHE_ENABLED,
        "regex": 0,
        "llm_cache": 0,
        "unresolved": 0,
        "with_resolution_risk_flags": 0,
    }
    if not LLM_CACHE_ENABLED:
        return stats

    for market in markets:
        source = market.get("metadata_source")
        if source == LLM_MATCH_METHOD:
            stats["llm_cache"] += 1
            if market.get("resolution_risk_flags"):
                stats["with_resolution_risk_flags"] += 1
        elif market.get("event_key"):
            stats["regex"] += 1
        else:
            stats["unresolved"] += 1

    return stats
