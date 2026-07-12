# Multi-venue macro matching and arbitrage detection.
from collections import defaultdict

import event_matching
import matching
from config import ENRICH_LIQUIDITY_ON_SCAN, MAX_HOLD_DAYS_BY_CATEGORY, MIN_MACRO_PROFIT, MIN_MATCH_CONFIDENCE
from crosswalk import match_from_crosswalk
from fees import build_two_venue_buy_plan, two_venue_arbitrage_cost
from market_categories import filter_by_enabled_categories
from macro_scoring import enrich_opportunity, passes_liquidity_filters, passes_macro_filters
from market_liquidity import enrich_opportunities_liquidity
from outcome_normalization import attach_event_metadata


def _attach_platform(markets, platform):
    for market in markets:
        market["platform"] = platform
    return markets


def _pair_key(market_a, market_b):
    id_a = market_a.get("ticker") or market_a.get("condition_id") or market_a.get("conid") or market_a["market_question"]
    id_b = market_b.get("ticker") or market_b.get("condition_id") or market_b.get("conid") or market_b["market_question"]
    return tuple(sorted((str(id_a), str(id_b))))


def match_markets_two_venue(markets_a, markets_b, platform_a, platform_b, quiet=False):
    """
    Match equivalent markets between two venues using event clusters + title matching.
    """
    for market in markets_a:
        attach_event_metadata(market)
    for market in markets_b:
        attach_event_metadata(market)

    pairs = []

    # Event-cluster pairs (highest confidence).
    clusters_a = event_matching.cluster_markets_by_event(markets_a)
    clusters_b = event_matching.cluster_markets_by_event(markets_b)
    matched_events = event_matching.match_event_clusters(clusters_a, clusters_b)
    cluster_pairs = event_matching.build_equivalent_market_pairs_generic(
        matched_events, platform_a, platform_b
    )
    pairs.extend(cluster_pairs)

    # Crosswalk + title fallback for Polymarket x Kalshi (richest manual/fuzzy coverage).
    if {platform_a, platform_b} == {"Polymarket", "Kalshi"}:
        poly_is_a = platform_a == "Polymarket"
        poly_markets = markets_a if poly_is_a else markets_b
        kalshi_markets = markets_b if poly_is_a else markets_a

        crosswalk = match_from_crosswalk(poly_markets, kalshi_markets, min_confidence=MIN_MATCH_CONFIDENCE)
        for pair in crosswalk:
            pairs.append({
                **pair,
                "platform_a": platform_a,
                "platform_b": platform_b,
                "market_a": pair["polymarket"] if poly_is_a else pair["kalshi"],
                "market_b": pair["kalshi"] if poly_is_a else pair["polymarket"],
            })

        title_pairs = matching.match_markets(poly_markets, kalshi_markets, quiet=True)
        for pair in title_pairs:
            if pair.get("confidence", 0) < MIN_MATCH_CONFIDENCE:
                continue
            pairs.append({
                **pair,
                "platform_a": platform_a,
                "platform_b": platform_b,
                "market_a": pair["polymarket"] if poly_is_a else pair["kalshi"],
                "market_b": pair["kalshi"] if poly_is_a else pair["polymarket"],
            })

    # Deduplicate.
    combined = {}
    for pair in pairs:
        key = _pair_key(pair["market_a"], pair["market_b"])
        existing = combined.get(key)
        if existing is None or pair.get("confidence", 0) > existing.get("confidence", 0):
            combined[key] = pair

    result = list(combined.values())
    if not quiet:
        print(f"  {platform_a} x {platform_b}: {len(result)} matched pairs")
    return result


def find_cross_venue_arbs(
    pairs,
    max_hold_days,
    min_profit=MIN_MACRO_PROFIT,
    min_annualized_return=0.0,
):
    """Run fee-aware arb math on matched pairs from any two venues."""
    opportunities = []

    for pair in pairs:
        market_a = pair["market_a"]
        market_b = pair["market_b"]
        platform_a = pair.get("platform_a", market_a.get("platform", "A"))
        platform_b = pair.get("platform_b", market_b.get("platform", "B"))

        arb = two_venue_arbitrage_cost(market_a, market_b, platform_a, platform_b)
        best = arb["best_strategy"]
        if best["profit"] <= 0:
            continue

        buy_plan = build_two_venue_buy_plan(
            best["strategy"],
            market_a,
            market_b,
            platform_a,
            platform_b,
            best,
        )

        category = pair.get("market_a", {}).get("category") or pair.get("market_b", {}).get("category")
        max_hold = MAX_HOLD_DAYS_BY_CATEGORY.get(category, max_hold_days)

        opportunity = {
            "type": "cross_venue_macro",
            "market_a": market_a,
            "market_b": market_b,
            "platform_a": platform_a,
            "platform_b": platform_b,
            "strategy": best["strategy"],
            "profit": best["profit"],
            "total_cost": best["total_cost"],
            "yes_fee": best["yes_fee"],
            "no_fee": best["no_fee"],
            "buy_plan": buy_plan,
            "event_label": pair.get("event_label"),
            "event_type": pair.get("event_type"),
            "match_method": pair.get("match_method"),
            "confidence": pair.get("confidence", 0.85),
            "polymarket_outcome": pair.get("polymarket_outcome"),
            "kalshi_outcome": pair.get("kalshi_outcome"),
            "category": category,
        }

        if passes_macro_filters(opportunity, max_hold, min_profit, min_annualized_return):
            enrich_opportunity(opportunity)
            opportunities.append(opportunity)

    opportunities.sort(key=lambda item: item.get("score", 0), reverse=True)
    return opportunities


def build_all_venue_pairs(kalshi_markets, poly_markets, forecastex_markets, quiet=False):
    """Match macro markets across all venue combinations."""
    for market in kalshi_markets:
        attach_event_metadata(market)
    for market in poly_markets:
        attach_event_metadata(market)
    for market in forecastex_markets:
        attach_event_metadata(market)

    kalshi_before = len(kalshi_markets)
    kalshi = filter_by_enabled_categories(_attach_platform(list(kalshi_markets), "Kalshi"))
    poly_before = len(poly_markets)
    poly = filter_by_enabled_categories(_attach_platform(list(poly_markets), "Polymarket"))
    fex_before = len(forecastex_markets)
    fex = filter_by_enabled_categories(_attach_platform(list(forecastex_markets), "ForecastEx"))

    kalshi_funnel = {
        "clean_extracted": kalshi_before,
        "category_passed": len(kalshi),
        "dropped_category": kalshi_before - len(kalshi),
    }

    if not quiet:
        print(f"Category markets: Kalshi={len(kalshi)}, Polymarket={len(poly)}, ForecastEx={len(fex)}")
        if kalshi_funnel["dropped_category"]:
            print(f"  Kalshi category filter dropped {kalshi_funnel['dropped_category']} markets")

    all_pairs = []
    if poly and kalshi:
        all_pairs.extend(match_markets_two_venue(poly, kalshi, "Polymarket", "Kalshi", quiet=quiet))
    if poly and fex:
        all_pairs.extend(match_markets_two_venue(poly, fex, "Polymarket", "ForecastEx", quiet=quiet))
    if kalshi and fex:
        all_pairs.extend(match_markets_two_venue(kalshi, fex, "Kalshi", "ForecastEx", quiet=quiet))

    # Dedupe across match methods.
    deduped = {}
    for pair in all_pairs:
        key = _pair_key(pair["market_a"], pair["market_b"])
        if key not in deduped or pair.get("confidence", 0) > deduped[key].get("confidence", 0):
            deduped[key] = pair

    return {
        "kalshi_macro": kalshi,
        "polymarket_macro": poly,
        "forecastex_macro": fex,
        "pairs": list(deduped.values()),
        "kalshi_funnel": kalshi_funnel,
        "poly_before_category": poly_before,
        "fex_before_category": fex_before,
    }


def scan_macro_arbitrage(
    kalshi_markets,
    poly_markets,
    forecastex_markets,
    max_hold_days,
    min_profit,
    min_annualized_return,
    quiet=False,
):
    """Full macro scan: filter, match, arb, rank."""
    bundle = build_all_venue_pairs(
        kalshi_markets,
        poly_markets,
        forecastex_markets,
        quiet=quiet,
    )
    opportunities = find_cross_venue_arbs(
        bundle["pairs"],
        max_hold_days=max_hold_days,
        min_profit=min_profit,
        min_annualized_return=min_annualized_return,
    )

    if ENRICH_LIQUIDITY_ON_SCAN and opportunities:
        if not quiet:
            print(f"Enriching {len(opportunities)} opportunities with liquidity data...")
        opportunities = enrich_opportunities_liquidity(opportunities)
        filtered = []
        for opportunity in opportunities:
            if passes_liquidity_filters(opportunity):
                enrich_opportunity(opportunity)
                filtered.append(opportunity)
        opportunities = filtered
        opportunities.sort(key=lambda item: item.get("score", 0), reverse=True)

    return {
        **bundle,
        "opportunities": opportunities,
    }
