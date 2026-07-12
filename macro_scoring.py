# Rank macro arbs by capital efficiency (annualized return, hold period).
from market_utils import days_until_resolution


def resolution_days(market):
    """Days until market resolves; fallback to large number if unknown."""
    for field in ("days_to_resolution",):
        value = market.get(field)
        if value is not None:
            try:
                days = float(value)
                if days >= 0:
                    return max(days, 0.25)
            except (TypeError, ValueError):
                pass

    for field in ("end_date", "close_time", "occurrence_datetime"):
        days = days_until_resolution(market.get(field))
        if days is not None and days >= 0:
            return max(days, 0.25)

    return 365.0


def pair_hold_days(market_a, market_b):
    """Conservative hold estimate: longer of the two resolution horizons."""
    return max(resolution_days(market_a), resolution_days(market_b))


def annualized_return(profit, hold_days):
    """Simple annualized return on deployed capital for a locked arb."""
    if hold_days <= 0 or profit <= 0:
        return 0.0
    return (profit / hold_days) * 365.0


def score_opportunity(profit, hold_days, confidence=1.0):
    """Composite score for ranking: annualized return weighted by match confidence."""
    base = annualized_return(profit, hold_days)
    return round(base * confidence, 4)


def enrich_opportunity(opportunity, confidence=None):
    """Attach hold_days, annualized_return_pct, and score to an opportunity dict."""
    if opportunity.get("type") == "cross_platform":
        poly = opportunity.get("polymarket") or opportunity.get("market_a", {})
        kalshi = opportunity.get("kalshi") or opportunity.get("market_b", {})
        hold = pair_hold_days(poly, kalshi)
    elif "market_a" in opportunity and "market_b" in opportunity:
        hold = pair_hold_days(opportunity["market_a"], opportunity["market_b"])
    else:
        hold = resolution_days(opportunity)

    profit = opportunity.get("profit", 0.0)
    conf = confidence if confidence is not None else opportunity.get("confidence", 1.0)

    opportunity["hold_days"] = round(hold, 2)
    opportunity["annualized_return"] = round(annualized_return(profit, hold), 4)
    opportunity["annualized_return_pct"] = round(opportunity["annualized_return"] * 100, 2)
    opportunity["score"] = score_opportunity(profit, hold, conf)
    return opportunity


def passes_macro_filters(
    opportunity,
    max_hold_days,
    min_profit,
    min_annualized_return,
):
    """Apply macro pipeline quality gates."""
    enrich_opportunity(opportunity)
    if opportunity["profit"] < min_profit:
        return False
    if opportunity["hold_days"] > max_hold_days:
        return False
    if opportunity["annualized_return"] < min_annualized_return:
        return False
    return True
