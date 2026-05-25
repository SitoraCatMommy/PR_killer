"""Unit tests for PR evidence grounding (2–5 quotes, no low-evidence rows)."""

from app.services.pr_grounding_service import build_pr_grounding


def test_pr_grounding_min_two_quotes() -> None:
    quotes = [
        {
            "type": "problem",
            "title": "price worry",
            "text": "We worry about the subscription price and billing clarity each month",
            "entity_id": "e1",
            "source_document_id": "d1",
            "chunk_id": "c1",
        },
        {
            "type": "problem",
            "title": "support",
            "text": "Support response time is slow when we have billing questions",
            "entity_id": "e2",
            "source_document_id": "d1",
            "chunk_id": "c2",
        },
    ]
    strategy = {
        "key_pr_insights": ["Users worry about subscription price and billing"],
        "reputational_risks": ["Negative perception of support and billing"],
        "recommended_messages": ["Be transparent on pricing and improve support"],
    }
    out = build_pr_grounding(strategy, quotes)
    for row in out:
        assert 2 <= len(row["evidence"]) <= 5


def test_pr_grounding_omits_low_evidence() -> None:
    """No quotes matching → row omitted (not 1 evidence)."""
    out = build_pr_grounding(
        {"key_pr_insights": ["completely unmatched xyz phrase alpha beta"]},
        [
            {
                "type": "topic",
                "title": "t",
                "text": "unrelated long enough text for minimum length for scoring",
                "entity_id": "a",
            }
        ],
    )
    assert out == []

