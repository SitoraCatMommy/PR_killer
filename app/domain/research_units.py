"""Primary research extraction categories (report-oriented, not NER)."""

from __future__ import annotations

from app.domain.enums import EntityType

PRIMARY_RESEARCH_ENTITY_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.USER_NEED,
        EntityType.BEHAVIOR_PATTERN,
        EntityType.TRUST_ISSUE,
        EntityType.ADOPTION_BARRIER,
        EntityType.RISK,
        EntityType.HYPOTHESIS,
        EntityType.RECOMMENDATION,
        EntityType.OPPORTUNITY,
        EntityType.OPEN_QUESTION,
        EntityType.SUPPORTING_FACT,
        EntityType.SENTIMENT_SIGNAL,
    }
)

LEGACY_ENTITY_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.PERSON,
        EntityType.ORGANIZATION,
        EntityType.LOCATION,
        EntityType.DATE,
        EntityType.TOPIC,
        EntityType.CLAIM,
        EntityType.METRIC,
        EntityType.REFERENCE,
        EntityType.CUSTOM,
    }
)
