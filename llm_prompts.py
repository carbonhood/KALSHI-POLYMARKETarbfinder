# Prompt templates for canonical market extraction.
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "canonical_market.json"

SYSTEM_PROMPT = """You extract structured metadata from prediction-market contracts for cross-venue matching.

Return a single JSON object matching this schema:
- event_type: one of central_bank, econ_release, econ_threshold, election, crypto_threshold, sports_pm, legal_outcome, geopolitical, threshold, other
- event_id: stable snake_case id for the underlying real-world event (NOT the market id)
- entities: structured fields needed to identify the event (institution, year, month, indicator, state, teams, asset, etc.)
- outcome.label: canonical outcome slug for THIS contract leg (e.g. hold, hike, hike_small, cut, above_3_0, team_a_win, convicted)
- outcome.kind: binary | bucket | threshold | team_win | candidate | other
- resolution: optional summary, cutoff ISO date, and named source if stated in rules
- confidence: 0-1 how sure you are about event_id AND outcome.label together
- resolution_risk_flags: list of risks like aggregate_vs_sized_bucket, headline_vs_core, ambiguous_cutoff
- evidence: short quote from title/rules supporting the extraction

Rules:
- Use rules_primary and description when present; do not invent settlement details.
- For central bank meetings: entities need institution, year, month. Outcomes: hold, hike, cut, hike_small, hike_large, cut_small, cut_large (sized buckets when subtitle specifies bps range).
- For econ releases (CPI, NFP, unemployment): event_type econ_release with indicator, year, month. Bucket outcomes like exact_0_3, above_0_3, below_0_2.
- For elections: event_type election with race_type (senate_race, house_race, governor_race, chamber_control, etc.), state if applicable, year, party or candidate in outcome when relevant.
- For crypto: crypto_threshold with asset, direction, strike value.
- For sports game winners: sports_pm with league, team_a, team_b, date; outcome label is winning team slug.
- For legal: legal_outcome with subject slug and verb (convicted, indicted, etc.).
- For unstructured geopolitics/world events: geopolitical with a specific event_id describing the event (e.g. trump_xi_meeting_2026).
- If ambiguous, lower confidence below 0.7 and add resolution_risk_flags.
- Never merge different resolution triggers into one event_id.
- Output JSON only, no markdown."""


def build_user_prompt(market_payload):
    lines = [
        "Extract canonical metadata for this market:",
        "",
        f"Platform: {market_payload.get('platform')}",
        f"Market ID: {market_payload.get('market_id')}",
        f"Question: {market_payload.get('market_question')}",
    ]
    optional_fields = (
        ("Event title", "event_title"),
        ("Event ticker", "event_ticker"),
        ("Yes subtitle", "yes_sub_title"),
        ("Group item title", "group_item_title"),
        ("Rules", "rules_primary"),
        ("Description", "description"),
        ("Resolution source", "resolution_source"),
        ("End date", "end_date"),
        ("Occurrence", "occurrence_datetime"),
    )
    for label, key in optional_fields:
        value = market_payload.get(key)
        if value:
            lines.append(f"{label}: {value}")

    tags = market_payload.get("tags") or []
    if tags:
        lines.append(f"Tags: {', '.join(str(tag) for tag in tags[:12])}")

    return "\n".join(lines)
