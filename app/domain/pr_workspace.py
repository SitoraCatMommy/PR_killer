"""PR workspace: which entity types appear in product UI and synthesis by default."""

from __future__ import annotations

from app.domain.enums import EntityType

# Hidden from default entity list API (not shown in PR strategist workspace).
DEFAULT_LIST_EXCLUDED_ENTITY_TYPES: frozenset[EntityType] = frozenset({EntityType.SUPPORTING_FACT})

# Synthesis / key signals: PR-strategist core (insights, risks, patterns, hypotheses family).
PR_SYNTHESIS_ENTITY_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.PROBLEM,
        EntityType.PAIN_POINT,
        EntityType.USER_NEED,
        EntityType.BEHAVIOR_PATTERN,
        EntityType.TRUST_ISSUE,
        EntityType.ADOPTION_BARRIER,
        EntityType.RISK,
        EntityType.HYPOTHESIS,
        EntityType.OPEN_QUESTION,
        EntityType.SENTIMENT_SIGNAL,
    }
)
