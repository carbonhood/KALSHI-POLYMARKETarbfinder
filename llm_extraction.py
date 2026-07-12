# On-demand LLM extraction for prediction markets (never called during scheduled scans).
import json
import os
import time

import requests

from config import (
    LLM_API_BASE,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_REQUEST_DELAY_SECONDS,
    LLM_REQUEST_TIMEOUT_SECONDS,
)
from extraction_validator import validate_extraction
from llm_extraction_cache import get_cached_record, save_cached_record
from llm_market_payload import build_market_payload, summarize_payload
from llm_prompts import SYSTEM_PROMPT, build_user_prompt


class LLMExtractionError(RuntimeError):
    pass


def get_api_key():
    return os.environ.get("OPENAI_API_KEY", "").strip()


def llm_available():
    return bool(get_api_key())


def _parse_json_content(content):
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def call_extraction_api(market_payload):
    """Call OpenAI-compatible chat completions API and return parsed JSON."""
    api_key = get_api_key()
    if not api_key:
        raise LLMExtractionError("OPENAI_API_KEY is not set")

    url = f"{LLM_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(market_payload)},
        ],
    }

    last_error = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 429:
                delay = LLM_REQUEST_DELAY_SECONDS * (2 ** attempt)
                time.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            return _parse_json_content(content)
        except (requests.RequestException, KeyError, json.JSONDecodeError, IndexError) as exc:
            last_error = exc
            if attempt + 1 < LLM_MAX_RETRIES:
                time.sleep(LLM_REQUEST_DELAY_SECONDS * (attempt + 1))

    raise LLMExtractionError(f"LLM extraction failed after retries: {last_error}")


def extract_market_with_llm(market, force=False):
    """
    Extract and cache a single market. Returns result dict with status.

    Status values: cached, extracted, invalid, skipped_no_api_key, error
    """
    if not force:
        cached = get_cached_record(market)
        if cached is not None:
            return {
                "status": "cached",
                "cache_key": cached["cache_key"],
                "valid": cached["valid"],
                "extraction": cached["extraction"],
                "validation_errors": cached["validation_errors"],
            }

    if not llm_available():
        return {"status": "skipped_no_api_key", "cache_key": None}

    payload = build_market_payload(market)
    try:
        extraction = call_extraction_api(payload)
    except LLMExtractionError as exc:
        return {"status": "error", "error": str(exc), "summary": summarize_payload(market)}

    valid, errors = validate_extraction(extraction)
    save_cached_record(
        market,
        extraction,
        valid=valid,
        validation_errors=errors,
        model=LLM_MODEL,
    )

    if LLM_REQUEST_DELAY_SECONDS > 0:
        time.sleep(LLM_REQUEST_DELAY_SECONDS)

    return {
        "status": "extracted" if valid else "invalid",
        "cache_key": None,
        "valid": valid,
        "extraction": extraction,
        "validation_errors": errors,
    }


def enrich_markets(
    markets,
    force=False,
    only_missing=True,
    limit=None,
    progress_callback=None,
):
    """
    Populate cache for a list of markets. Returns summary stats dict.
    """
    from outcome_normalization import extract_event_key

    stats = {
        "requested": 0,
        "cached": 0,
        "extracted": 0,
        "invalid": 0,
        "skipped_regex_ok": 0,
        "skipped_no_api_key": 0,
        "errors": 0,
        "error_samples": [],
    }

    candidates = []
    for market in markets:
        if only_missing and not force:
            if extract_event_key(market) is not None:
                stats["skipped_regex_ok"] += 1
                continue
            if get_cached_record(market) is not None:
                stats["cached"] += 1
                continue
        candidates.append(market)

    if limit is not None:
        candidates = candidates[: max(0, int(limit))]

    stats["requested"] = len(candidates)

    for index, market in enumerate(candidates, start=1):
        result = extract_market_with_llm(market, force=force)
        status = result.get("status")

        if status == "cached":
            stats["cached"] += 1
        elif status == "extracted":
            stats["extracted"] += 1
        elif status == "invalid":
            stats["invalid"] += 1
        elif status == "skipped_no_api_key":
            stats["skipped_no_api_key"] += 1
            break
        elif status == "error":
            stats["errors"] += 1
            if len(stats["error_samples"]) < 5:
                stats["error_samples"].append(result.get("error") or result.get("summary"))

        if progress_callback:
            progress_callback(index, len(candidates), market, result)

    return stats
