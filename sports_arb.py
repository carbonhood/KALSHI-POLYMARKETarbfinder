# Cross-book and Kalshi-vs-book sports arbitrage detection.
from config import (
    BOOKMAKER_COMMISSIONS,
    DEFAULT_BOOK_COMMISSION,
    MIN_SPORTS_ARB_PROFIT,
)
from fees import kalshi_taker_fee, kalshi_fee_multiplier
from sports_team_match import find_matching_event, kalshi_outcome_team, normalize_team, team_match_score


def effective_decimal_odds(decimal_odds, commission=DEFAULT_BOOK_COMMISSION):
    """
    Adjust decimal back odds for exchange commission on winnings.

    Returns effective decimal odds (lower = worse for backer = higher implied prob).
    """
    if decimal_odds is None or decimal_odds <= 1:
        return None
    return 1 + (decimal_odds - 1) * (1 - commission)


def implied_probability(decimal_odds, commission=DEFAULT_BOOK_COMMISSION):
    effective = effective_decimal_odds(decimal_odds, commission)
    if not effective or effective <= 0:
        return None
    return 1.0 / effective


def _book_commission(bookmaker_key):
    return BOOKMAKER_COMMISSIONS.get(bookmaker_key, DEFAULT_BOOK_COMMISSION)


def _extract_h2h_outcomes(event):
    """Return {outcome_name: (best_decimal_odds, bookmaker_key, bookmaker_title)}."""
    best = {}

    for bookmaker in event.get("bookmakers", []):
        key = bookmaker.get("key", "")
        title = bookmaker.get("title", key)
        commission = _book_commission(key)

        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue

            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")
                if name is None or price is None:
                    continue

                try:
                    decimal_price = float(price)
                except (TypeError, ValueError):
                    continue

                effective = effective_decimal_odds(decimal_price, commission)
                if effective is None:
                    continue

                current = best.get(name)
                if current is None or effective > current[0]:
                    best[name] = (effective, decimal_price, key, title, commission)

    return best


def find_cross_book_arbs(events, min_profit=MIN_SPORTS_ARB_PROFIT):
    """
    Classic surebet: best back odds per outcome across all books.

    For outcomes O1..On, arb exists when sum(1/effective_decimal_i) < 1.
    """
    opportunities = []

    for event in events:
        best = _extract_h2h_outcomes(event)
        if len(best) < 2:
            continue

        implied_sum = sum(1.0 / info[0] for info in best.values())
        profit = 1.0 - implied_sum
        if profit < min_profit:
            continue

        total_implied = implied_sum
        legs = []
        for outcome_name, (effective, raw_decimal, book_key, book_title, comm) in best.items():
            stake_fraction = (1.0 / effective) / total_implied
            legs.append({
                "outcome": outcome_name,
                "bookmaker": book_title,
                "bookmaker_key": book_key,
                "decimal_odds": raw_decimal,
                "effective_decimal": round(effective, 4),
                "commission": comm,
                "stake_fraction": round(stake_fraction, 4),
            })

        opportunities.append({
            "type": "cross_book_surebet",
            "sport_key": event.get("_sport_key") or event.get("sport_key"),
            "event": f"{event.get('home_team')} vs {event.get('away_team')}",
            "commence_time": event.get("commence_time"),
            "profit": round(profit, 5),
            "implied_sum": round(implied_sum, 5),
            "legs": legs,
            "buy_plan": {
                "summary": f"Surebet: {event.get('home_team')} vs {event.get('away_team')}",
                "legs": [
                    {
                        "platform": leg["bookmaker"],
                        "side": leg["outcome"],
                        "price": leg["decimal_odds"],
                        "stake_fraction": leg["stake_fraction"],
                    }
                    for leg in legs
                ],
            },
        })

    opportunities.sort(key=lambda item: item["profit"], reverse=True)
    return opportunities


def find_kalshi_vs_book_arbs(kalshi_markets, odds_events, min_profit=MIN_SPORTS_ARB_PROFIT):
    """
    Compare Kalshi YES ask (one team) vs best book odds on other outcomes.

    For 2-outcome without draw: cost = kalshi_yes + 1/best_effective_opponent < 1
    For 3-outcome: try kalshi YES on team A + best books on other two outcomes.
    """
    opportunities = []

    for kalshi_market in kalshi_markets:
        match = find_matching_event(kalshi_market, odds_events)
        if not match:
            continue

        event, match_score = match
        best = _extract_h2h_outcomes(event)
        if len(best) < 2:
            continue

        yes_team = kalshi_outcome_team(kalshi_market)
        if not yes_team:
            continue

        kalshi_yes = kalshi_market.get("yes_price")
        if not kalshi_yes or kalshi_yes <= 0:
            continue

        fee_mult = kalshi_market.get("fee_multiplier") or kalshi_fee_multiplier(
            kalshi_market.get("ticker")
        )
        kalshi_fee = kalshi_taker_fee(kalshi_yes, fee_multiplier=fee_mult)
        kalshi_cost = kalshi_yes + kalshi_fee

        matched_outcome = None
        for outcome_name in best:
            if team_match_score(yes_team, outcome_name) >= 0.75:
                matched_outcome = outcome_name
                break

        if not matched_outcome:
            continue

        other_outcomes = {
            name: info for name, info in best.items()
            if name != matched_outcome
        }
        if not other_outcomes:
            continue

        other_cost = sum(1.0 / info[0] for info in other_outcomes.values())
        total_cost = kalshi_cost + other_cost
        profit = 1.0 - total_cost

        if profit < min_profit:
            continue

        legs = [{
            "platform": "Kalshi",
            "side": f"YES ({matched_outcome})",
            "market": kalshi_market.get("market_question"),
            "price": kalshi_yes,
            "fee": kalshi_fee,
            "total": round(kalshi_cost, 5),
        }]

        for outcome_name, (effective, raw_decimal, book_key, book_title, comm) in other_outcomes.items():
            legs.append({
                "platform": book_title,
                "side": outcome_name,
                "decimal_odds": raw_decimal,
                "effective_decimal": round(effective, 4),
                "cost_per_dollar_payout": round(1.0 / effective, 5),
                "commission": comm,
            })

        opportunities.append({
            "type": "kalshi_vs_books",
            "sport_key": event.get("_sport_key") or event.get("sport_key"),
            "event": f"{event.get('home_team')} vs {event.get('away_team')}",
            "commence_time": event.get("commence_time"),
            "match_score": round(match_score, 2),
            "kalshi_ticker": kalshi_market.get("ticker"),
            "profit": round(profit, 5),
            "total_cost": round(total_cost, 5),
            "legs": legs,
            "buy_plan": {
                "summary": (
                    f"Kalshi YES {matched_outcome} + cover other outcomes on books "
                    f"({event.get('home_team')} vs {event.get('away_team')})"
                ),
                "legs": legs,
            },
        })

    opportunities.sort(key=lambda item: item["profit"], reverse=True)
    return opportunities


def filter_kalshi_sports_markets(kalshi_markets):
    """Keep Kalshi markets that look like head-to-head sports."""
    sports = []
    for market in kalshi_markets:
        title = market.get("market_question", "").lower()
        if " vs " in title or " vs. " in title:
            sports.append(market)
            continue
        if market.get("yes_sub_title") and market.get("event_ticker", "").startswith("KX"):
            if any(tag in title for tag in ("win", "winner", "beat", "game")):
                sports.append(market)
    return sports
