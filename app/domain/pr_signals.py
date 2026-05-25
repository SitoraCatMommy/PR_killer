"""PR-facing extraction taxonomy (signals used for insight → evidence → action)."""

from __future__ import annotations

from enum import StrEnum

from app.domain.enums import EntityType


class PRSignalTaxonomy(StrEnum):
    """Allowed labels in extraction JSON ``entity_type`` for PR research pipeline."""

    RISK_SIGNAL = "risk_signal"
    TRUST_DRIVER = "trust_driver"
    OBJECTION = "objection"
    REPUTATION_THREAT = "reputation_threat"
    MESSAGE_RESONANCE = "message_resonance"
    PROOF_POINT = "proof_point"
    CHANNEL_PREFERENCE = "channel_preference"


PR_SIGNAL_VALUES: tuple[str, ...] = tuple(sorted(e.value for e in PRSignalTaxonomy))

# Persist as EntityType + tags_json["pr_signal"] for DB / dashboards.
PR_SIGNAL_TO_ENTITY_TYPE: dict[PRSignalTaxonomy, EntityType] = {
    PRSignalTaxonomy.RISK_SIGNAL: EntityType.RISK,
    PRSignalTaxonomy.TRUST_DRIVER: EntityType.TRUST_ISSUE,
    PRSignalTaxonomy.OBJECTION: EntityType.ADOPTION_BARRIER,
    PRSignalTaxonomy.REPUTATION_THREAT: EntityType.RISK,
    PRSignalTaxonomy.MESSAGE_RESONANCE: EntityType.BEHAVIOR_PATTERN,
    PRSignalTaxonomy.PROOF_POINT: EntityType.SUPPORTING_FACT,
    PRSignalTaxonomy.CHANNEL_PREFERENCE: EntityType.USER_NEED,
}


def coerce_pr_signal(raw: str) -> PRSignalTaxonomy | None:
    s = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return PRSignalTaxonomy(s)
    except ValueError:
        return None


ENTITY_TYPE_FALLBACK_PR: dict[EntityType, PRSignalTaxonomy] = {
    EntityType.PROBLEM: PRSignalTaxonomy.RISK_SIGNAL,
    EntityType.PAIN_POINT: PRSignalTaxonomy.RISK_SIGNAL,
    EntityType.RISK: PRSignalTaxonomy.RISK_SIGNAL,
    EntityType.TRUST_ISSUE: PRSignalTaxonomy.TRUST_DRIVER,
    EntityType.ADOPTION_BARRIER: PRSignalTaxonomy.OBJECTION,
    EntityType.USER_NEED: PRSignalTaxonomy.CHANNEL_PREFERENCE,
    EntityType.BEHAVIOR_PATTERN: PRSignalTaxonomy.MESSAGE_RESONANCE,
    EntityType.SUPPORTING_FACT: PRSignalTaxonomy.PROOF_POINT,
    EntityType.SENTIMENT_SIGNAL: PRSignalTaxonomy.RISK_SIGNAL,
    EntityType.HYPOTHESIS: PRSignalTaxonomy.MESSAGE_RESONANCE,
    EntityType.RECOMMENDATION: PRSignalTaxonomy.MESSAGE_RESONANCE,
    EntityType.OPPORTUNITY: PRSignalTaxonomy.MESSAGE_RESONANCE,
    EntityType.OPEN_QUESTION: PRSignalTaxonomy.OBJECTION,
}


def taxonomy_label_for_entity(entity_type: EntityType, tags_json: dict | None) -> str:
    tj = dict(tags_json or {})
    raw = str(tj.get("pr_signal") or "").strip()
    pr = coerce_pr_signal(raw)
    if pr is not None:
        return pr.value
    fb = ENTITY_TYPE_FALLBACK_PR.get(entity_type)
    return fb.value if fb else PRSignalTaxonomy.PROOF_POINT.value
