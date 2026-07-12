# Extract structured entities from market titles for cross-platform matching.
import re
import string

TEAM_SUFFIXES = (
    " republic", " united", " city", " fc", " sc", " cf", " ac",
    " athletic", " sporting", " club", " team", " the",
)

OUTCOME_ALIASES = {
    "tie": "draw",
    "draw": "draw",
    "tied": "draw",
}

VS_PATTERNS = [
    re.compile(
        r"(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)(?:\s+winner|\?|$|\(|:|\s+men'?s|\s+women'?s|\s+professional|\s+match|\s+game)",
        re.IGNORECASE,
    ),
    re.compile(
        r"win\s+(?:the\s+)?(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)(?:\s+men'?s|\s+women'?s|\s+professional|\s+match|\s+game|\?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?):\s",
        re.IGNORECASE,
    ),
]

WIN_ON_DATE_PATTERN = re.compile(
    r"will\s+(?P<team>.+?)\s+win\s+on\s+\d{4}-\d{2}-\d{2}",
    re.IGNORECASE,
)

THRESHOLD_PATTERN = re.compile(
    r"(?:above|over|below|under|at least|more than)\s+\$?(?P<amount>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)

RANGE_PATTERN = re.compile(
    r"\bbetween\b|\bfrom\b.*\bto\b|\b\d+(?:\.\d+)?%?\s*(?:and|-)\s*\d+(?:\.\d+)?%?",
    re.IGNORECASE,
)

THRESHOLD_DIRECTION_PATTERN = re.compile(
    r"\b(above|over|below|under|at least|more than|less than)\b",
    re.IGNORECASE,
)

OUTCOME_QUESTION_PATTERN = re.compile(
    r"will\s+(?P<outcome>.+?)\s+(?:be|win|wins|won)\b",
    re.IGNORECASE,
)

DRAW_PATTERN = re.compile(
    r"\b(?:end in a draw|ends in a draw|draw\?|tie\?|ends in a tie)\b",
    re.IGNORECASE,
)


def _strip_punctuation(text):
    cleaned = text.lower()
    for char in string.punctuation:
        cleaned = cleaned.replace(char, " ")
    return " ".join(cleaned.split())


def normalize_entity(name):
    """Normalize team/player names so small formatting differences still match."""
    if not name:
        return ""

    text = _strip_punctuation(name)
    for suffix in TEAM_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()

    return text


def normalize_outcome(name):
    text = normalize_entity(name)
    return OUTCOME_ALIASES.get(text, text)


def extract_matchup(title):
    """
    Return sorted (team_a, team_b) from titles like:
    - Tulsa vs Sacramento Republic Winner?
    - UFC 329: Max Holloway vs. Conor McGregor (...)
    """
    if not title:
        return None

    title_candidates = [title]
    if ":" in title:
        title_candidates.insert(0, title.split(":", 1)[1])

    for candidate_title in title_candidates:
        for pattern in VS_PATTERNS:
            match = pattern.search(candidate_title)
            if not match:
                continue

            team_a = normalize_entity(match.group("a"))
            team_b = normalize_entity(match.group("b"))
            team_a = _trim_leading_preamble(team_a)
            team_b = _trim_leading_preamble(team_b)

            if len(team_a) >= 3 and len(team_b) >= 3:
                return tuple(sorted((team_a, team_b)))

    return None


def infer_outcome_from_win_on_date(title):
    """Extract team name from 'Will TEAM win on YYYY-MM-DD?' questions."""
    if not title:
        return None

    match = WIN_ON_DATE_PATTERN.search(title)
    if not match:
        return None

    return normalize_entity(match.group("team"))


def _trim_leading_preamble(text):
    """Drop prefixes like 'will the los angeles beat win the'."""
    words = text.split()
    if len(words) <= 4:
        return text

    for idx, word in enumerate(words):
        if word == "vs" or word == "vs.":
            left = " ".join(words[:idx])
            if " win the " in f" {left} ":
                left = left.split(" win the ", 1)[-1]
            return left.strip()

    if " win the " in text:
        return text.split(" win the ", 1)[-1].strip()

    return text


def extract_outcome(title, group_item_title=None, yes_sub_title=None):
    """Identify which side/outcome a binary market is about."""
    if yes_sub_title:
        return normalize_outcome(yes_sub_title)

    if group_item_title:
        return normalize_entity(group_item_title)

    if title and DRAW_PATTERN.search(title):
        return "draw"

    win_on_date = infer_outcome_from_win_on_date(title)
    if win_on_date:
        return win_on_date

    if title:
        match = OUTCOME_QUESTION_PATTERN.search(title)
        if match:
            return normalize_entity(match.group("outcome"))

    return None


def extract_threshold(title):
    """Extract numeric strike/threshold markets like 'above $9500'."""
    if not title:
        return None

    match = THRESHOLD_PATTERN.search(title)
    if not match:
        return None

    amount = match.group("amount").replace(",", "")
    try:
        value = float(amount)
    except ValueError:
        return None

    if value.is_integer():
        value = int(value)
    return value


def has_range_structure(title):
    return bool(title and RANGE_PATTERN.search(title))


def has_directional_threshold(title):
    return bool(title and THRESHOLD_DIRECTION_PATTERN.search(title))


def has_incompatible_resolution_structure(title_a, title_b):
    """
    Reject pairs where one market is a range bucket and the other is a
    single-sided threshold, or directional thresholds use different values.
    """
    if not title_a or not title_b:
        return False

    range_a = has_range_structure(title_a)
    range_b = has_range_structure(title_b)
    if range_a != range_b:
        return True

    directional_a = has_directional_threshold(title_a)
    directional_b = has_directional_threshold(title_b)
    if directional_a and directional_b:
        threshold_a = extract_threshold(title_a)
        threshold_b = extract_threshold(title_b)
        if threshold_a is not None and threshold_b is not None and threshold_a != threshold_b:
            return True

    return False


def extract_subject_tokens(title):
    """
    Pull subject tokens for threshold/topic matching.
    Example: world cup final ticketdata july 18th
    """
    if not title:
        return set()

    text = _strip_punctuation(title)
    stopwords = {
        "will", "the", "be", "on", "at", "et", "pm", "am", "this", "week",
        "above", "below", "over", "under", "more", "than", "get", "in",
        "price", "of", "to", "a", "an", "and", "or", "for", "from", "between",
    }
    tokens = {
        word
        for word in text.split()
        if len(word) >= 3 and word not in stopwords and not word.isdigit()
    }
    return tokens


def build_match_signature(title, group_item_title=None, yes_sub_title=None, event_matchup=None):
    """
    Build a structured signature used for entity-based matching.

    Returns dict with matchup, outcome, threshold, and subject tokens.
    """
    matchup = extract_matchup(title) or event_matchup
    outcome = extract_outcome(title, group_item_title, yes_sub_title)

    return {
        "matchup": matchup,
        "outcome": outcome,
        "threshold": extract_threshold(title),
        "subject_tokens": extract_subject_tokens(title),
    }


def matchup_outcome_key(signature):
    matchup = signature.get("matchup")
    outcome = signature.get("outcome")
    if not matchup or not outcome:
        return None
    return (matchup, outcome)


def threshold_subject_key(signature):
    threshold = signature.get("threshold")
    subject_tokens = signature.get("subject_tokens") or set()
    if threshold is None or len(subject_tokens) < 2:
        return None

    core_tokens = tuple(sorted(token for token in subject_tokens if len(token) >= 4)[:6])
    if len(core_tokens) < 2:
        core_tokens = tuple(sorted(subject_tokens)[:4])
    if len(core_tokens) < 2:
        return None

    return (threshold, core_tokens)


def attach_entity_metadata(market, title_field="market_question"):
    """Attach _entity signature fields to a normalized market dict."""
    title = market.get(title_field, "")
    signature = build_match_signature(
        title,
        group_item_title=market.get("group_item_title"),
        yes_sub_title=market.get("yes_sub_title"),
        event_matchup=market.get("event_matchup"),
    )
    market["_entity"] = signature
    market["_matchup_outcome_key"] = matchup_outcome_key(signature)
    market["_threshold_subject_key"] = threshold_subject_key(signature)
    return market
