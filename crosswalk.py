# Manual event crosswalk: highest-confidence matching layer.
import json
import re
from pathlib import Path

from config import CROSSWALK_PATH, MATCH_CONFIDENCE, MIN_MATCH_CONFIDENCE
from outcome_normalization import outcomes_are_equivalent

_crosswalk_cache = None


def _normalize_lookup(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def load_crosswalk(path=CROSSWALK_PATH):
    global _crosswalk_cache
    if _crosswalk_cache is not None:
        return _crosswalk_cache

    file_path = Path(path)
    if not file_path.exists():
        _crosswalk_cache = {"version": "1.1", "events": []}
        return _crosswalk_cache

    with open(file_path, "r", encoding="utf-8") as file:
        _crosswalk_cache = json.load(file)
    return _crosswalk_cache


def _title_matches_rules(title, rules, market=None):
    lowered = _normalize_lookup(title)

    for phrase in rules.get("title_must_contain_all", []):
        if _normalize_lookup(phrase) not in lowered:
            return False

    if rules.get("title_must_contain_any"):
        if not any(_normalize_lookup(p) in lowered for p in rules["title_must_contain_any"]):
            return False

    if rules.get("title_must_contain"):
        if _normalize_lookup(rules["title_must_contain"]) not in lowered:
            return False

    for phrase in rules.get("title_must_not_contain", []):
        if _normalize_lookup(phrase) in lowered:
            return False

    group_item = (market or {}).get("group_item_title") or ""
    required_group = rules.get("group_item_title")
    if required_group and _normalize_lookup(group_item) != _normalize_lookup(required_group):
        return False

    return True


def _markets_for_side(side_rules, markets):
    return [
        market for market in markets
        if _title_matches_rules(market.get("market_question", ""), side_rules, market=market)
    ]


def _outcome_label(market, rules=None):
    if rules and rules.get("prefer_yes_sub_title") and market.get("yes_sub_title"):
        return _normalize_lookup(market["yes_sub_title"])

    if market.get("group_item_title"):
        return _normalize_lookup(market["group_item_title"])

    if market.get("yes_sub_title"):
        return _normalize_lookup(market["yes_sub_title"])

    return _normalize_lookup(market.get("canonical_outcome") or "")


def _map_outcome(label, outcome_map):
    if not label:
        return None
    if label in outcome_map:
        return outcome_map[label]

    for source, canonical in outcome_map.items():
        if source in label or label in source:
            return canonical

    return label.replace(" ", "_")


def _build_pair(poly_market, kalshi_market, entry, confidence, poly_outcome, kalshi_outcome):
    return {
        "polymarket": poly_market,
        "kalshi": kalshi_market,
        "match_method": "crosswalk",
        "crosswalk_id": entry["id"],
        "event_label": entry.get("label", entry["id"]),
        "polymarket_outcome": poly_outcome,
        "kalshi_outcome": kalshi_outcome,
        "confidence": confidence,
        "similarity": confidence,
        "match_score": 12,
    }


def _pairs_from_event_key(entry, poly_markets, kalshi_markets):
    event_key = tuple(entry["event_key"])
    confidence = entry.get("confidence", MATCH_CONFIDENCE["crosswalk"])
    pairs = []

    poly_in_event = [m for m in poly_markets if m.get("event_key") == event_key]
    kalshi_in_event = [m for m in kalshi_markets if m.get("event_key") == event_key]
    if not poly_in_event or not kalshi_in_event:
        return pairs

    for group in entry.get("outcome_groups", []):
        poly_outcomes = set(group.get("polymarket", []))
        kalshi_outcomes = set(group.get("kalshi", []))

        for poly_market in poly_in_event:
            poly_outcome = poly_market.get("canonical_outcome")
            if poly_outcome not in poly_outcomes:
                continue

            for kalshi_market in kalshi_in_event:
                kalshi_outcome = kalshi_market.get("canonical_outcome")
                if kalshi_outcome not in kalshi_outcomes:
                    continue
                if not outcomes_are_equivalent(poly_outcome, kalshi_outcome):
                    if poly_outcome != kalshi_outcome:
                        continue

                pairs.append(_build_pair(
                    poly_market, kalshi_market, entry, confidence,
                    poly_outcome, kalshi_outcome,
                ))

    return pairs


def _pairs_from_title_rules(entry, poly_markets, kalshi_markets):
    kalshi_rules = entry.get("kalshi")
    poly_rules = entry.get("polymarket")
    if not kalshi_rules or not poly_rules:
        return []

    kalshi_matches = _markets_for_side(kalshi_rules, kalshi_markets)
    poly_matches = _markets_for_side(poly_rules, poly_markets)
    if not kalshi_matches or not poly_matches:
        return []

    outcome_map = entry.get("outcomes", {})
    confidence = entry.get("confidence", MATCH_CONFIDENCE["crosswalk"])
    pairs = []

    if outcome_map.get("match_field") == "yes_sub_title_or_group_item":
        poly_by_outcome = {}
        for market in poly_matches:
            label = _outcome_label(market)
            poly_by_outcome.setdefault(label, []).append(market)

        kalshi_by_outcome = {}
        for market in kalshi_matches:
            label = _outcome_label(market, kalshi_rules)
            kalshi_by_outcome.setdefault(label, []).append(market)

        for poly_label, poly_list in poly_by_outcome.items():
            for kalshi_label, kalshi_list in kalshi_by_outcome.items():
                poly_canonical = _map_outcome(poly_label, outcome_map)
                kalshi_canonical = _map_outcome(kalshi_label, outcome_map)
                if poly_canonical != kalshi_canonical:
                    continue

                for poly_market in poly_list:
                    for kalshi_market in kalshi_list:
                        pairs.append(_build_pair(
                            poly_market, kalshi_market, entry, confidence,
                            poly_canonical, kalshi_canonical,
                        ))
        return pairs

    for poly_market in poly_matches:
        poly_outcome = _map_outcome(_outcome_label(poly_market), outcome_map)
        for kalshi_market in kalshi_matches:
            kalshi_outcome = _map_outcome(_outcome_label(kalshi_market, kalshi_rules), outcome_map)
            if poly_outcome != kalshi_outcome:
                continue
            pairs.append(_build_pair(
                poly_market, kalshi_market, entry, confidence,
                poly_outcome, kalshi_outcome,
            ))

    return pairs


def match_from_crosswalk(polymarket_markets, kalshi_markets, min_confidence=MIN_MATCH_CONFIDENCE):
    """Apply manual crosswalk rules and return high-confidence market pairs."""
    crosswalk = load_crosswalk()
    pairs = []
    seen = set()

    for entry in crosswalk.get("events", []):
        if entry.get("event_key"):
            entry_pairs = _pairs_from_event_key(entry, polymarket_markets, kalshi_markets)
        else:
            entry_pairs = _pairs_from_title_rules(entry, polymarket_markets, kalshi_markets)

        for pair in entry_pairs:
            if pair["confidence"] < min_confidence:
                continue

            key = (
                pair["polymarket"].get("condition_id") or pair["polymarket"]["market_question"],
                pair["kalshi"].get("ticker") or pair["kalshi"]["market_question"],
            )
            if key in seen:
                continue
            seen.add(key)
            pairs.append(pair)

    return pairs
