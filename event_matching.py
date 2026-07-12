# Cluster markets into events and match clusters across platforms.
from collections import defaultdict

from config import LLM_MATCH_METHOD, MATCH_CONFIDENCE
from outcome_normalization import attach_event_metadata, outcomes_are_equivalent


def _pair_match_metadata(market_a, market_b):
    """Confidence and method for a pair inside a matched event cluster."""
    llm_sources = [
        market for market in (market_a, market_b)
        if market.get("metadata_source") == LLM_MATCH_METHOD
    ]
    if llm_sources:
        confidences = [
            market.get("llm_confidence") or MATCH_CONFIDENCE["llm_cache_equivalent_outcome"]
            for market in llm_sources
        ]
        return "llm_cache_equivalent_outcome", min(confidences)
    return "event_cluster_equivalent_outcome", MATCH_CONFIDENCE["event_cluster_equivalent_outcome"]


def cluster_markets_by_event(markets):
    """Group markets by canonical event_key."""
    clusters = defaultdict(list)
    for market in markets:
        attach_event_metadata(market)
        event_key = market.get("event_key")
        if event_key:
            clusters[event_key].append(market)
    return dict(clusters)


def _event_label(event_key):
    if not event_key:
        return "unknown"

    if event_key[0] == "central_bank":
        _, bank_id, year, month = event_key
        return f"{bank_id.replace('_', ' ').title()} ({year}-{month:02d})"
    if event_key[0] == "econ_threshold":
        _, indicator, year, month, direction, value = event_key
        label = indicator.replace("_", " ").title()
        return f"{label} {direction} {value} ({year}-{month:02d})"
    if event_key[0] == "econ_release":
        _, indicator, year, month = event_key
        label = indicator.replace("_", " ").title()
        return f"{label} release ({year}-{month:02d})"
    if event_key[0] == "sports_match":
        _, team_a, team_b, game_date = event_key
        return f"{team_a} vs {team_b} on {game_date}"
    if event_key[0] == "esports_match":
        _, teams, game_date = event_key
        return f"{' vs '.join(teams)} (esports) on {game_date}"
    if event_key[0] == "golf_tournament":
        _, tournament_id, year = event_key
        return f"{tournament_id.replace('_', ' ').title()} {year}"
    if event_key[0] == "threshold":
        _, subject_parts, direction, threshold = event_key
        return f"{'/'.join(subject_parts)} {direction} {threshold}"
    if event_key[0] == "election":
        _, race_type, *rest = event_key
        label = race_type.replace("_", " ").title()
        if race_type in {"senate_race", "house_race", "governor_race", "governor_primary"}:
            state, year = rest[0], rest[1]
            return f"{label} {state.upper()} ({year})"
        if race_type == "chamber_control":
            chamber, year = rest[0], rest[1]
            return f"{chamber.title()} control ({year})"
        return f"{label} {rest}"
    if event_key[0] == "crypto_threshold":
        _, asset, direction, value = event_key
        return f"{asset.upper()} {direction} {value}"
    if event_key[0] == "sports_pm":
        _, league, team_a, team_b, game_date = event_key
        return f"{league.upper()} {team_a} vs {team_b} ({game_date})"
    if event_key[0] == "legal_outcome":
        _, subject, verb = event_key
        return f"{subject} — {verb}"
    if event_key[0] == "geopolitical":
        _, slug = event_key
        return slug.replace("_", " ").title()
    if event_key[0] == "other":
        _, slug = event_key
        return slug.replace("_", " ").title()
    return str(event_key)


def match_event_clusters(clusters_a, clusters_b):
    """
    Match event clusters that share the same canonical event_key.

    Returns list of dicts with markets_a and markets_b.
    """
    matched = []
    shared_keys = set(clusters_a) & set(clusters_b)

    for event_key in sorted(shared_keys):
        markets_a = clusters_a[event_key]
        markets_b = clusters_b[event_key]
        if not markets_a or not markets_b:
            continue

        matched.append({
            "event_key": event_key,
            "event_label": _event_label(event_key),
            "event_type": event_key[0],
            "markets_a": markets_a,
            "markets_b": markets_b,
            # Backward-compatible aliases.
            "polymarket_markets": markets_a,
            "kalshi_markets": markets_b,
        })

    return matched


def build_equivalent_market_pairs(matched_events):
    """
    Within matched events, pair markets that share the same canonical outcome.

    These pairs are safe inputs for standard 2-leg cross-platform arb math.
    """
    pairs = []

    for event in matched_events:
        poly_by_outcome = defaultdict(list)
        kalshi_by_outcome = defaultdict(list)

        for market in event["polymarket_markets"]:
            outcome = market.get("canonical_outcome")
            if outcome:
                poly_by_outcome[outcome].append(market)

        for market in event["kalshi_markets"]:
            outcome = market.get("canonical_outcome")
            if outcome:
                kalshi_by_outcome[outcome].append(market)

        seen_outcomes = set()
        for poly_outcome, poly_markets in poly_by_outcome.items():
            for kalshi_outcome, kalshi_markets in kalshi_by_outcome.items():
                if not outcomes_are_equivalent(poly_outcome, kalshi_outcome):
                    continue

                pair_key = (poly_outcome, kalshi_outcome)
                if pair_key in seen_outcomes:
                    continue
                seen_outcomes.add(pair_key)

                for poly_market in poly_markets:
                    for kalshi_market in kalshi_markets:
                        match_method, confidence = _pair_match_metadata(poly_market, kalshi_market)
                        pairs.append({
                            "polymarket": poly_market,
                            "kalshi": kalshi_market,
                            "match_method": match_method,
                            "confidence": confidence,
                            "event_key": event["event_key"],
                            "event_label": event["event_label"],
                            "event_type": event["event_type"],
                            "polymarket_outcome": poly_outcome,
                            "kalshi_outcome": kalshi_outcome,
                            "similarity": 1.0,
                            "match_score": 10,
                        })

    return pairs


def build_equivalent_market_pairs_generic(matched_events, platform_a="A", platform_b="B"):
    """
    Like build_equivalent_market_pairs but works for any two venues.

    matched_events items must have markets_a and markets_b lists.
    """
    pairs = []

    for event in matched_events:
        markets_a = event.get("markets_a") or event.get("polymarket_markets", [])
        markets_b = event.get("markets_b") or event.get("kalshi_markets", [])

        by_outcome_a = defaultdict(list)
        by_outcome_b = defaultdict(list)

        for market in markets_a:
            outcome = market.get("canonical_outcome")
            if outcome:
                by_outcome_a[outcome].append(market)

        for market in markets_b:
            outcome = market.get("canonical_outcome")
            if outcome:
                by_outcome_b[outcome].append(market)

        seen_outcomes = set()
        for outcome_a, list_a in by_outcome_a.items():
            for outcome_b, list_b in by_outcome_b.items():
                if not outcomes_are_equivalent(outcome_a, outcome_b):
                    continue
                pair_key = (outcome_a, outcome_b)
                if pair_key in seen_outcomes:
                    continue
                seen_outcomes.add(pair_key)

                for market_a in list_a:
                    for market_b in list_b:
                        match_method, confidence = _pair_match_metadata(market_a, market_b)
                        pairs.append({
                            "market_a": market_a,
                            "market_b": market_b,
                            "platform_a": platform_a,
                            "platform_b": platform_b,
                            "match_method": match_method,
                            "confidence": confidence,
                            "event_key": event["event_key"],
                            "event_label": event["event_label"],
                            "event_type": event["event_type"],
                            "polymarket_outcome": outcome_a,
                            "kalshi_outcome": outcome_b,
                            "similarity": 1.0,
                            "match_score": 10,
                        })

    return pairs


def match_events(polymarket_markets, kalshi_markets, quiet=False):
    """
    Full event-level pipeline: cluster, match events, emit equivalent market pairs.
    """
    poly_clusters = cluster_markets_by_event(polymarket_markets)
    kalshi_clusters = cluster_markets_by_event(kalshi_markets)
    matched_events = match_event_clusters(poly_clusters, kalshi_clusters)
    pairs = build_equivalent_market_pairs(matched_events)

    if not quiet:
        print(f"Polymarket event clusters: {len(poly_clusters)}")
        print(f"Kalshi event clusters: {len(kalshi_clusters)}")
        print(f"Matched cross-platform events: {len(matched_events)}")
        for event in matched_events:
            print(f"  - {event['event_label']}")
        print(f"Equivalent cross-platform market pairs: {len(pairs)}")

    return {
        "polymarket_clusters": poly_clusters,
        "kalshi_clusters": kalshi_clusters,
        "matched_events": matched_events,
        "pairs": pairs,
    }
