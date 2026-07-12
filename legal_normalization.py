# Canonical event keys for legal / court outcome markets.
import re

from entity_matching import normalize_entity

CONVICT_PATTERN = re.compile(
    r"will (?P<subject>.+?)\s+(?:be\s+)?(?P<verb>convicted|indicted|charged|acquitted|sentenced|found guilty)",
    re.I,
)
SAME_SUBJECT_VERB = re.compile(
    r"(?P<subject>.+?).{0,30}(?P<verb>convicted|indicted|charged|acquitted|sentenced|found guilty)",
    re.I,
)


def _normalize_verb(verb):
    mapping = {
        "convicted": "convicted",
        "found guilty": "convicted",
        "indicted": "indicted",
        "charged": "charged",
        "acquitted": "acquitted",
        "sentenced": "sentenced",
    }
    return mapping.get((verb or "").lower().strip(), normalize_entity(verb))


def extract_legal_event_key(title, market=None):
    """
    Return ('legal_outcome', subject, verb) when both platforms frame the same case.
    """
    combined = f"{title or ''} {(market or {}).get('event_title', '')}"
    match = CONVICT_PATTERN.search(combined) or SAME_SUBJECT_VERB.search(combined)
    if not match:
        return None

    subject = normalize_entity(match.group("subject"))
    verb = _normalize_verb(match.group("verb"))
    if len(subject) < 3:
        return None
    return ("legal_outcome", subject, verb)


def normalize_legal_outcome(title, market=None):
    event_key = (market or {}).get("event_key") or extract_legal_event_key(title, market=market)
    if not event_key or event_key[0] != "legal_outcome":
        return None
    return event_key[2]
