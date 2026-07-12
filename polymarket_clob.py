# Fetch executable ask prices from the Polymarket CLOB.
import requests

from config import POLYMARKET_CLOB_BATCH_SIZE

CLOB_PRICES_URL = "https://clob.polymarket.com/prices"


def fetch_buy_prices(token_ids):
    """
    Return best ask (BUY side) prices for many CLOB token IDs.

    The CLOB accepts batches of {"token_id", "side": "BUY"} payloads.
    """
    prices = {}
    unique_token_ids = []
    seen = set()
    for token_id in token_ids:
        if not token_id or token_id in seen:
            continue
        seen.add(token_id)
        unique_token_ids.append(str(token_id))

    for start in range(0, len(unique_token_ids), POLYMARKET_CLOB_BATCH_SIZE):
        batch = unique_token_ids[start:start + POLYMARKET_CLOB_BATCH_SIZE]
        payload = [{"token_id": token_id, "side": "BUY"} for token_id in batch]
        response = requests.post(CLOB_PRICES_URL, json=payload, timeout=60)
        response.raise_for_status()
        page = response.json()

        for token_id, sides in page.items():
            buy_price = sides.get("BUY")
            if buy_price is not None:
                prices[token_id] = float(buy_price)

    return prices


def prices_from_tokens(yes_token_id, no_token_id, price_lookup):
    """Resolve YES/NO ask prices for one binary market."""
    yes_price = price_lookup.get(str(yes_token_id))
    no_price = price_lookup.get(str(no_token_id))
    if yes_price is None or no_price is None:
        return None
    if yes_price <= 0 or no_price <= 0:
        return None
    return yes_price, no_price
