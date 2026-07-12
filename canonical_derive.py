# Map LLM canonical extractions to pipeline event_key + canonical_outcome tuples.
import re

from entity_matching import normalize_entity
from llm_market_payload import slugify_event_id


def _int_or_none(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    except (TypeError, ValueError):
        return None


def _normalize_outcome_label(label):
    if not label:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return cleaned or None


def derive_from_extraction(extraction):
    """
    Convert validated canonical extraction JSON into event_key and canonical_outcome.

    Returns dict with keys: event_key, canonical_outcome, event_id, confidence, resolution_risk_flags
    """
    if not extraction:
        return {}

    event_type = extraction.get("event_type")
    entities = extraction.get("entities") or {}
    outcome = extraction.get("outcome") or {}
    outcome_label = _normalize_outcome_label(outcome.get("label"))
    event_id = extraction.get("event_id") or slugify_event_id(extraction.get("evidence"))

    event_key = None
    if event_type == "central_bank":
        institution = entities.get("institution") or entities.get("bank")
        year = _int_or_none(entities.get("year"))
        month = _int_or_none(entities.get("month"))
        if institution and year and month:
            institution = slugify_event_id(institution)
            event_key = ("central_bank", institution, year, month)

    elif event_type == "econ_release":
        indicator = entities.get("indicator")
        year = _int_or_none(entities.get("year"))
        month = _int_or_none(entities.get("month"))
        if indicator and year and month:
            event_key = ("econ_release", slugify_event_id(indicator), year, month)

    elif event_type == "econ_threshold":
        indicator = entities.get("indicator")
        year = _int_or_none(entities.get("year"))
        month = _int_or_none(entities.get("month"))
        direction = entities.get("direction")
        value = _float_or_none(entities.get("value"))
        if indicator and year and month and direction and value is not None:
            event_key = (
                "econ_threshold",
                slugify_event_id(indicator),
                year,
                month,
                str(direction).lower(),
                value,
            )

    elif event_type == "election":
        race_type = entities.get("race_type")
        year = _int_or_none(entities.get("year"))
        if race_type and year:
            race_type = slugify_event_id(race_type)
            state = entities.get("state")
            party = entities.get("party")
            candidate = entities.get("candidate")
            if race_type in {"senate_race", "house_race", "governor_race", "governor_primary"} and state:
                event_key = ("election", race_type, str(state).upper(), year)
            elif race_type == "chamber_control":
                chamber = entities.get("chamber") or "chamber"
                event_key = ("election", race_type, slugify_event_id(chamber), year)
            elif race_type == "endorsement" and candidate:
                event_key = (
                    "election",
                    race_type,
                    slugify_event_id(candidate),
                    slugify_event_id(entities.get("office") or "office"),
                    year,
                )
            elif party:
                event_key = ("election", race_type, slugify_event_id(party), year)

    elif event_type == "crypto_threshold":
        asset = entities.get("asset")
        direction = entities.get("direction")
        value = _float_or_none(entities.get("value") or entities.get("strike"))
        if asset and direction and value is not None:
            event_key = ("crypto_threshold", slugify_event_id(asset), str(direction).lower(), value)

    elif event_type == "sports_pm":
        league = entities.get("league")
        team_a = normalize_entity(entities.get("team_a") or "")
        team_b = normalize_entity(entities.get("team_b") or "")
        game_date = entities.get("date") or entities.get("game_date")
        if league and team_a and team_b and game_date:
            event_key = ("sports_pm", slugify_event_id(league), team_a, team_b, str(game_date)[:10])

    elif event_type == "legal_outcome":
        subject = normalize_entity(entities.get("subject") or "")
        verb = slugify_event_id(entities.get("verb") or "")
        if subject and verb:
            event_key = ("legal_outcome", subject, verb)

    elif event_type == "geopolitical":
        slug = slugify_event_id(event_id)
        if slug and slug != "unknown_event":
            event_key = ("geopolitical", slug)

    elif event_type == "threshold":
        subject_parts = entities.get("subject_parts") or entities.get("subjects") or []
        direction = entities.get("direction")
        value = _float_or_none(entities.get("value"))
        if subject_parts and direction and value is not None:
            parts = tuple(slugify_event_id(part) for part in subject_parts if part)
            if parts:
                event_key = ("threshold", parts, str(direction).lower(), value)

    elif event_type == "other":
        slug = slugify_event_id(event_id)
        if slug and slug != "unknown_event":
            event_key = ("other", slug)

    return {
        "event_key": event_key,
        "canonical_outcome": outcome_label,
        "event_id": event_id,
        "confidence": extraction.get("confidence"),
        "resolution_risk_flags": list(extraction.get("resolution_risk_flags") or []),
        "event_type": event_type,
    }
