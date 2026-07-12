# Build normalized LLM input payloads from venue market dicts.
import hashlib
import json
import re


def _platform_name(market):
    return market.get("platform") or "Unknown"


def market_id(market):
    """Stable venue-native identifier for cache keys."""
    platform = _platform_name(market)
    if platform == "Kalshi":
        return str(market.get("ticker") or "")
    if platform == "Polymarket":
        return str(market.get("condition_id") or "")
    if platform == "ForecastEx":
        return str(market.get("conid") or "")
    return ""


def _fallback_id(market):
    question = (market.get("market_question") or "").strip().lower()
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
    return f"hash_{digest}"


def cache_key_for_market(market):
    platform = _platform_name(market)
    mid = market_id(market) or _fallback_id(market)
    return f"{platform}:{mid}"


def content_hash_for_market(market):
    """Hash fields that affect extraction output."""
    payload = build_market_payload(market)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_market_payload(market):
    """Minimal, consistent payload sent to the extraction model."""
    platform = _platform_name(market)
    payload = {
        "platform": platform,
        "market_id": market_id(market) or _fallback_id(market),
        "market_question": market.get("market_question") or "",
        "event_title": market.get("event_title") or "",
        "event_ticker": market.get("event_ticker") or "",
        "yes_sub_title": market.get("yes_sub_title") or "",
        "group_item_title": market.get("group_item_title") or "",
        "rules_primary": market.get("rules_primary") or "",
        "description": market.get("description") or "",
        "resolution_source": market.get("resolution_source") or "",
        "tags": market.get("tags") or [],
        "end_date": market.get("end_date") or market.get("close_time") or "",
        "occurrence_datetime": market.get("occurrence_datetime") or "",
    }
    return payload


def summarize_payload(market):
    """One-line summary for logs."""
    question = (market.get("market_question") or "")[:80]
    return f"{cache_key_for_market(market)} | {question}"


def slugify_event_id(text):
    cleaned = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return cleaned[:120] or "unknown_event"
