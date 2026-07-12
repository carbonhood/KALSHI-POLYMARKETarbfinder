# Compares market titles from Polymarket and Kalshi to find likely pairs
# for the same real-world event.
import string
from collections import defaultdict
from difflib import SequenceMatcher

import event_matching
from config import MATCH_CONFIDENCE, MIN_MATCH_CONFIDENCE
from crosswalk import match_from_crosswalk
from entity_matching import attach_entity_metadata, has_incompatible_resolution_structure
from outcome_normalization import attach_event_metadata

# Stores the final matched pairs after match_markets() runs.
matched_markets = []

# Common English words that do not help identify a specific market.
FILLER_WORDS = {
    "will", "the", "is", "an", "a", "in", "by", "on", "at", "for", "to",
    "of", "or", "and", "be", "any", "before", "after", "over", "under",
    "next", "called", "held", "new", "it", "its", "that", "this", "from",
    "with", "as", "if", "than", "more", "less", "between", "into", "during",
    "through", "about", "when", "who", "what", "how", "does", "do", "did",
    "has", "have", "had", "been", "being", "are", "was", "were", "not", "no",
    "yes", "all", "some", "other", "their", "there", "they", "them", "his",
    "her", "she", "he", "we", "you", "your", "our", "can", "may", "should",
}

# Words that appear in many unrelated markets, so they create false matches.
GENERIC_WORDS = {
    "world", "cup", "fifa", "host", "hosts", "announced", "men", "mens",
    "women", "womens", "win", "wins", "won", "lose", "loses", "lost", "team",
    "teams", "game", "games", "season", "league", "champion", "championship",
    "final", "finals", "round", "match", "matches", "player", "players",
    "country", "countries", "state", "states", "city", "reported", "report",
    "year", "years", "month", "months", "day", "days", "time", "times",
    "price", "prices", "rate", "rates", "percent", "million", "billion",
    "democratic", "republican", "party", "national", "committee", "control",
    "senate", "house", "presidency", "presidential", "midterm", "election",
    "elections", "nomination", "primary", "person", "winner", "series",
    "open", "atp", "wta", "mlb", "nba", "nfl", "nhl", "mls", "ufc",
}

# Words that change what "Yes" means. Both sides must agree on these.
RESOLUTION_GROUPS = [
    {"impeach", "impeached", "impeachment"},
    {"remove", "removed", "removal"},
    {"leave", "leaves", "left", "depart", "departs", "departed"},
    {"resign", "resigns", "resigned", "resignation"},
    {"win", "wins", "won"},
    {"lose", "loses", "lost"},
    {"nominate", "nominated", "nomination"},
    {"convict", "convicted", "conviction"},
    {"indict", "indicted", "indictment"},
    {"charge", "charged"},
    {"acquit", "acquitted", "acquittal"},
    {"invade", "invades", "invaded", "invasion"},
    {"capture", "captures", "captured"},
    {"visit", "visits", "visited"},
    {"pregnant", "pregnancy"},
    {"ipo"},
    {"sentence", "sentenced", "sentencing"},
    {"arrest", "arrested"},
    {"advance", "advances", "advanced"},
    {"pass", "passed", "passes"},
    {"veto", "vetoed"},
    {"sign", "signed"},
    {"recognize", "recognizes", "recognized", "recognise", "recognises"},
    {"ban", "banned", "banning"},
    {"legalize", "legalized", "legalise", "legalised"},
    {"meet", "meets", "met"},
    {"talk", "talks", "talked"},
    {"join", "joins", "joined"},
    {"cut", "cuts", "cutting"},
    {"raise", "raises", "raised"},
    {"default", "defaults", "defaulted"},
]

# Extra words that narrow the event scope and must not differ across platforms.
SCOPE_WORDS = {
    "removed", "removal", "office", "cabinet", "administration", "ticket",
    "indicted", "convicted", "charged", "acquitted", "resign", "resigned",
    "pregnant", "visit", "ipo", "sentenced", "prison", "invade", "invaded",
    "capture", "captured", "host", "hosts", "advance", "passed", "vetoed",
    "signed", "annex", "annexed", "recognize", "recognized", "ban", "banned",
}

SHORT_KEYWORDS = {"uk", "eu", "us", "ai", "gta"}

WORD_TO_RESOLUTION_STEM = {}
for group in RESOLUTION_GROUPS:
    stem = min(group, key=len)
    for word in group:
        WORD_TO_RESOLUTION_STEM[word] = stem


def normalize_title(title):
    """Turn a title into a cleaned string for similarity comparison."""
    normalized = title.lower()
    for char in string.punctuation:
        normalized = normalized.replace(char, " ")

    return " ".join(
        word
        for word in normalized.split()
        if word not in FILLER_WORDS
    )


def extract_years(title):
    """Pull 4-digit years like 2026 out of a title."""
    normalized = title.lower()
    for char in string.punctuation:
        normalized = normalized.replace(char, " ")

    return {word for word in normalized.split() if len(word) == 4 and word.isdigit()}


def extract_keywords(title):
    """Convert a title into a set of useful whole-word keywords."""
    normalized = title.lower()
    for char in string.punctuation:
        normalized = normalized.replace(char, " ")

    return {
        word
        for word in normalized.split()
        if word not in FILLER_WORDS
        and not word.isdigit()
        and (len(word) >= 3 or word in SHORT_KEYWORDS)
    }


def extract_resolution_stems(words):
    """Map outcome verbs like 'impeached' and 'removed' to canonical stems."""
    return {
        WORD_TO_RESOLUTION_STEM[word]
        for word in words
        if word in WORD_TO_RESOLUTION_STEM
    }


def attach_match_metadata(markets):
    """Precompute keyword and entity metadata once per market."""
    for market in markets:
        attach_entity_metadata(market)
        words = extract_keywords(market["market_question"])
        market["_keywords"] = words
        market["_distinctive_keywords"] = words - GENERIC_WORDS
        market["_years"] = extract_years(market["market_question"])
    return markets


def build_kalshi_candidate_index(kalshi_markets):
    """
    Inverted index: distinctive keyword -> Kalshi market indices.

    Lets us skip the full cross-product and only score likely pairs.
    """
    index = defaultdict(set)
    for idx, market in enumerate(kalshi_markets):
        for keyword in market["_distinctive_keywords"]:
            index[keyword].add(idx)
    return index


def build_entity_indexes(kalshi_markets):
    """Index Kalshi markets by structured matchup/outcome and threshold keys."""
    matchup_outcome = defaultdict(list)
    threshold_subject = defaultdict(list)

    for idx, market in enumerate(kalshi_markets):
        key = market.get("_matchup_outcome_key")
        if key:
            matchup_outcome[key].append(idx)

        threshold_key = market.get("_threshold_subject_key")
        if threshold_key:
            threshold_subject[threshold_key].append(idx)

    return matchup_outcome, threshold_subject


def candidate_kalshi_indices(polymarket_market, kalshi_index):
    """Return Kalshi indices that share at least two distinctive keywords."""
    counts = defaultdict(int)
    for keyword in polymarket_market["_distinctive_keywords"]:
        for idx in kalshi_index.get(keyword, ()):
            counts[idx] += 1

    return [idx for idx, shared_count in counts.items() if shared_count >= 2]


def entity_candidate_indices(polymarket_market, matchup_outcome_index, threshold_subject_index):
    """Return Kalshi indices that match structured entity signatures."""
    indices = set()

    matchup_key = polymarket_market.get("_matchup_outcome_key")
    if matchup_key:
        indices.update(matchup_outcome_index.get(matchup_key, ()))

    threshold_key = polymarket_market.get("_threshold_subject_key")
    if threshold_key:
        indices.update(threshold_subject_index.get(threshold_key, ()))

    return sorted(indices)


# Prop-style markets resolve differently from simple winner markets.
PROP_MARKET_MARKERS = (
    "o/u",
    "over/under",
    "both teams to score",
    "exact score",
    "halftime",
    "neither team",
    "to score first",
    "spread:",
)


def is_prop_market(title):
    lowered = title.lower()
    return any(marker in lowered for marker in PROP_MARKET_MARKERS)


def has_incompatible_market_type(title_a, title_b):
    prop_a = is_prop_market(title_a)
    prop_b = is_prop_market(title_b)
    return prop_a != prop_b


def has_material_mismatch(polymarket_words, kalshi_words):
    """
    Reject pairs where one platform adds outcome or scope language the other lacks.
    """
    poly_only = polymarket_words - kalshi_words
    kalshi_only = kalshi_words - polymarket_words

    poly_material = (poly_only & SCOPE_WORDS) | (
        extract_resolution_stems(poly_only) - extract_resolution_stems(kalshi_words)
    )
    kalshi_material = (kalshi_only & SCOPE_WORDS) | (
        extract_resolution_stems(kalshi_only) - extract_resolution_stems(polymarket_words)
    )

    if poly_material or kalshi_material:
        return True

    poly_resolution = extract_resolution_stems(polymarket_words)
    kalshi_resolution = extract_resolution_stems(kalshi_words)
    if poly_resolution != kalshi_resolution:
        return True

    poly_only_distinctive = poly_only - GENERIC_WORDS
    kalshi_only_distinctive = kalshi_only - GENERIC_WORDS
    return bool(poly_only_distinctive and kalshi_only_distinctive)


def score_entity_match(polymarket_market, kalshi_market):
    """Strong match when structured entities align (same game/outcome/threshold)."""
    poly_key = polymarket_market.get("_matchup_outcome_key")
    kalshi_key = kalshi_market.get("_matchup_outcome_key")
    if poly_key and poly_key == kalshi_key:
        return {
            "match_method": "entity_matchup_outcome",
            "confidence": MATCH_CONFIDENCE["entity_matchup_outcome"],
            "shared_keywords": sorted(poly_key[0]),
            "distinctive_keywords": sorted(poly_key[0]),
            "poly_only_keywords": [],
            "kalshi_only_keywords": [],
            "resolution_stems": [],
            "match_score": 10,
            "overlap_ratio": 1.0,
            "similarity": 0.95,
        }

    poly_threshold = polymarket_market.get("_threshold_subject_key")
    kalshi_threshold = kalshi_market.get("_threshold_subject_key")
    if poly_threshold and poly_threshold == kalshi_threshold:
        return {
            "match_method": "entity_threshold_subject",
            "confidence": MATCH_CONFIDENCE["entity_threshold_subject"],
            "shared_keywords": sorted(str(part) for part in poly_threshold[1]),
            "distinctive_keywords": sorted(str(part) for part in poly_threshold[1]),
            "poly_only_keywords": [],
            "kalshi_only_keywords": [],
            "resolution_stems": [],
            "match_score": 9,
            "overlap_ratio": 1.0,
            "similarity": 0.93,
        }

    return None


def score_match(polymarket_market, kalshi_market):
    """
    Decide whether one Polymarket market and one Kalshi market likely refer
    to the same event. Returns match details, or None if they do not match.
    """
    polymarket_title = polymarket_market["market_question"]
    kalshi_title = kalshi_market["market_question"]
    if has_incompatible_resolution_structure(polymarket_title, kalshi_title):
        return None
    if has_incompatible_market_type(polymarket_title, kalshi_title):
        return None

    entity_match = score_entity_match(polymarket_market, kalshi_market)
    if entity_match is not None:
        return entity_match

    polymarket_words = polymarket_market["_keywords"]
    kalshi_words = kalshi_market["_keywords"]

    shared = polymarket_words & kalshi_words
    distinctive_shared = shared - GENERIC_WORDS

    similarity = SequenceMatcher(
        None,
        normalize_title(polymarket_title),
        normalize_title(kalshi_title),
    ).ratio()

    # Relaxed path for near-identical titles with meaningful shared tokens.
    if similarity >= 0.82 and len(distinctive_shared) >= 1 and len(shared) >= 2:
        if not has_material_mismatch(polymarket_words, kalshi_words):
            return {
                "match_method": "high_similarity",
                "confidence": MATCH_CONFIDENCE["high_similarity"],
                "shared_keywords": sorted(shared),
                "distinctive_keywords": sorted(distinctive_shared),
                "poly_only_keywords": sorted(polymarket_words - kalshi_words),
                "kalshi_only_keywords": sorted(kalshi_words - polymarket_words),
                "resolution_stems": sorted(extract_resolution_stems(polymarket_words)),
                "match_score": len(distinctive_shared),
                "overlap_ratio": round(len(shared) / max(min(len(polymarket_words), len(kalshi_words)), 1), 2),
                "similarity": round(similarity, 2),
            }

    if len(shared) < 2:
        return None

    if len(distinctive_shared) < 2:
        return None

    if has_material_mismatch(polymarket_words, kalshi_words):
        return None

    smaller_set_size = min(len(polymarket_words), len(kalshi_words))
    if smaller_set_size == 0:
        return None

    overlap_ratio = len(shared) / smaller_set_size
    if overlap_ratio < 0.55:
        return None

    polymarket_years = polymarket_market["_years"]
    kalshi_years = kalshi_market["_years"]
    if polymarket_years and kalshi_years and not (polymarket_years & kalshi_years):
        return None

    if similarity < 0.75:
        return None

    return {
        "match_method": "keyword_similarity",
        "confidence": MATCH_CONFIDENCE["keyword_similarity"],
        "shared_keywords": sorted(shared),
        "distinctive_keywords": sorted(distinctive_shared),
        "poly_only_keywords": sorted(polymarket_words - kalshi_words),
        "kalshi_only_keywords": sorted(kalshi_words - polymarket_words),
        "resolution_stems": sorted(extract_resolution_stems(polymarket_words)),
        "match_score": len(distinctive_shared),
        "overlap_ratio": round(overlap_ratio, 2),
        "similarity": round(similarity, 2),
    }


def _is_better_match(candidate, current_best):
    if current_best is None:
        return True

    method_rank = {
        "crosswalk": 6,
        "event_cluster_equivalent_outcome": 5,
        "llm_cache_equivalent_outcome": 4,
        "entity_matchup_outcome": 4,
        "entity_threshold_subject": 3,
        "high_similarity": 2,
        "keyword_similarity": 1,
    }
    candidate_rank = method_rank.get(candidate.get("match_method"), 0)
    best_rank = method_rank.get(current_best.get("match_method"), 0)
    if candidate_rank != best_rank:
        return candidate_rank > best_rank

    if candidate["similarity"] != current_best["similarity"]:
        return candidate["similarity"] > current_best["similarity"]

    return candidate["match_score"] > current_best["match_score"]


def match_markets(clean_markets_polymarket, clean_markets_kalshi, quiet=False):
    """
    For each Polymarket market, find the best Kalshi match and store the pair
    if it passes all matching rules.
    """
    if not quiet:
        print("Matching Polymarket and Kalshi markets")

    matched_markets.clear()
    attach_match_metadata(clean_markets_polymarket)
    attach_match_metadata(clean_markets_kalshi)
    kalshi_index = build_kalshi_candidate_index(clean_markets_kalshi)
    matchup_outcome_index, threshold_subject_index = build_entity_indexes(clean_markets_kalshi)

    for polymarket_market in clean_markets_polymarket:
        best_match = None
        candidate_indices = set(entity_candidate_indices(
            polymarket_market,
            matchup_outcome_index,
            threshold_subject_index,
        ))
        candidate_indices.update(candidate_kalshi_indices(polymarket_market, kalshi_index))

        for idx in candidate_indices:
            kalshi_market = clean_markets_kalshi[idx]
            match_details = score_match(polymarket_market, kalshi_market)
            if match_details is None:
                continue

            candidate = {
                "polymarket": polymarket_market,
                "kalshi": kalshi_market,
                **match_details,
            }

            if _is_better_match(candidate, best_match):
                best_match = candidate

        if best_match is not None:
            matched_markets.append(best_match)

    if not quiet:
        print(f"Total matched market pairs: {len(matched_markets)}")
    return matched_markets


def _pair_identity(pair):
    poly = pair["polymarket"]
    kalshi = pair["kalshi"]
    return (
        poly.get("condition_id") or poly.get("market_question"),
        kalshi.get("ticker") or kalshi.get("market_question"),
    )


def _attach_confidence(pair):
    if "confidence" not in pair:
        method = pair.get("match_method", "keyword_similarity")
        pair["confidence"] = MATCH_CONFIDENCE.get(method, 0.5)
    return pair


def match_all_markets(clean_markets_polymarket, clean_markets_kalshi, quiet=False):
    """
    Combine crosswalk, event-cluster, and title/entity matching.
    Crosswalk and event-cluster pairs are preferred when both exist.
    """
    if not quiet:
        print("Matching events and markets across platforms")

    for market in clean_markets_polymarket:
        attach_event_metadata(market)
    for market in clean_markets_kalshi:
        attach_event_metadata(market)

    crosswalk_pairs = match_from_crosswalk(
        clean_markets_polymarket,
        clean_markets_kalshi,
        min_confidence=MIN_MATCH_CONFIDENCE,
    )
    event_result = event_matching.match_events(
        clean_markets_polymarket,
        clean_markets_kalshi,
        quiet=True,
    )
    title_pairs = match_markets(
        clean_markets_polymarket,
        clean_markets_kalshi,
        quiet=True,
    )

    combined = {}
    for pair in crosswalk_pairs + event_result["pairs"] + title_pairs:
        pair = _attach_confidence(pair)
        if pair["confidence"] < MIN_MATCH_CONFIDENCE:
            continue
        key = _pair_identity(pair)
        existing = combined.get(key)
        if existing is None or _is_better_match(pair, existing):
            combined[key] = pair

    matched_markets.clear()
    matched_markets.extend(combined.values())

    if not quiet:
        print(f"Crosswalk pairs: {len(crosswalk_pairs)}")
        print(f"Event-cluster pairs: {len(event_result['pairs'])}")
        print(f"Title/entity pairs: {len(title_pairs)}")
        print(f"Total unique matched pairs (conf >= {MIN_MATCH_CONFIDENCE}): {len(matched_markets)}")
        for event in event_result["matched_events"]:
            print(f"  Shared event: {event['event_label']}")
        for pair in matched_markets:
            print(
                f"  [{pair.get('confidence', 0):.2f}] {pair.get('match_method')} | "
                f"{pair.get('event_label', pair['polymarket']['market_question'][:50])}"
            )

    return {
        "pairs": matched_markets,
        "matched_events": event_result["matched_events"],
        "crosswalk_pairs": crosswalk_pairs,
        "event_pairs": event_result["pairs"],
        "title_pairs": title_pairs,
    }
