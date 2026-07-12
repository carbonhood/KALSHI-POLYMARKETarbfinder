# Validate LLM extraction JSON before caching or matching.
import json
from pathlib import Path

from config import LLM_MIN_CONFIDENCE
from canonical_derive import derive_from_extraction

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

_SCHEMA = None
_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "canonical_market.json"


def _load_schema():
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH, encoding="utf-8") as file:
            _SCHEMA = json.load(file)
    return _SCHEMA


def validate_extraction(data):
    """
    Validate extraction dict. Returns (ok: bool, errors: list[str]).
    """
    errors = []
    if not isinstance(data, dict):
        return False, ["extraction must be a JSON object"]

    if jsonschema is not None:
        try:
            jsonschema.validate(instance=data, schema=_load_schema())
        except jsonschema.ValidationError as exc:
            errors.append(exc.message)
    else:
        for field in ("event_type", "event_id", "outcome", "confidence"):
            if field not in data:
                errors.append(f"missing required field: {field}")

    confidence = data.get("confidence")
    if confidence is not None and confidence < LLM_MIN_CONFIDENCE:
        errors.append(f"confidence {confidence} below minimum {LLM_MIN_CONFIDENCE}")

    outcome = data.get("outcome") or {}
    if not outcome.get("label"):
        errors.append("outcome.label is required")

    derived = derive_from_extraction(data)
    if not derived.get("event_key"):
        errors.append("could not derive event_key from extraction")

    risk_flags = data.get("resolution_risk_flags") or []
    high_risk = {"aggregate_vs_sized_bucket", "headline_vs_core", "different_data_source"}
    if high_risk.intersection(set(risk_flags)) and confidence and confidence >= 0.95:
        errors.append("high resolution risk flags with excessive confidence")

    return len(errors) == 0, errors
