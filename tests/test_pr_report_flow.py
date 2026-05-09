from __future__ import annotations

from uuid import uuid4

from app.domain.enums import EntityType
from app.models.extracted_entity import ExtractedEntity
from app.services.research_pipeline_orchestrator_service import build_pr_readiness_decision
from app.services.research_report_generation_service import (
    _bounded_user_payload_json,
    _report_data_validation_errors,
    _select_synthesis_entities,
)


def test_readiness_blocks_empty_project() -> None:
    decision = build_pr_readiness_decision(
        processable_count=0,
        chunk_count=0,
        pr_entity_count=0,
        min_pr_entity_count=3,
        needs_chunking_count=0,
        needs_extraction_count=0,
        low_signal_source_count=0,
        aggregation_exists=False,
    )

    assert decision["ready_for_report"] is False
    assert decision["blocking_reasons"] == ["no_processable_sources"]


def test_readiness_blocks_only_low_signal_entities() -> None:
    decision = build_pr_readiness_decision(
        processable_count=1,
        chunk_count=4,
        pr_entity_count=0,
        min_pr_entity_count=3,
        needs_chunking_count=0,
        needs_extraction_count=0,
        low_signal_source_count=1,
        aggregation_exists=True,
    )

    assert decision["ready_for_report"] is False
    assert "low_pr_signal" in decision["blocking_reasons"]
    assert "sources_have_only_low_signal_entities" in decision["warnings"]


def test_readiness_allows_report_with_missing_aggregation_warning() -> None:
    decision = build_pr_readiness_decision(
        processable_count=2,
        chunk_count=8,
        pr_entity_count=5,
        min_pr_entity_count=3,
        needs_chunking_count=0,
        needs_extraction_count=0,
        low_signal_source_count=0,
        aggregation_exists=False,
    )

    assert decision["ready_for_report"] is True
    assert decision["blocking_reasons"] == []
    assert decision["warnings"] == ["aggregation_missing"]


def _entity(entity_type: EntityType, title: str) -> ExtractedEntity:
    return ExtractedEntity(
        project_id=uuid4(),
        source_document_id=uuid4(),
        chunk_id=uuid4(),
        entity_type=entity_type,
        title=title,
        content=title,
        confidence_score=0.8,
        tags_json={},
        evidence_json={"quote": title},
    )


def test_synthesis_selection_ignores_supporting_facts_when_pr_signals_exist() -> None:
    supporting = [_entity(EntityType.SUPPORTING_FACT, f"fact {i}") for i in range(5)]
    signal = _entity(EntityType.RISK, "trust risk")

    selected = _select_synthesis_entities([*supporting, signal])

    assert selected == [signal]


def test_bounded_payload_trims_low_priority_sections() -> None:
    payload = {
        "analysis_mode": "smart_synthesis",
        "synthesis_input": {
            "key_signals": [f"signal {i}" * 20 for i in range(80)],
            "evidence_quotes": [{"quote": f"quote {i}" * 50} for i in range(80)],
            "recurring_patterns": [{"pattern": f"pattern {i}"} for i in range(80)],
            "top_topics": [f"topic {i}" for i in range(80)],
            "external_research_seeds": [f"seed {i}" for i in range(80)],
            "word_frequency_block": {
                "word_frequency": {f"word{i}": i for i in range(80)},
                "themed_buckets": {"risk": {f"risk{i}": i for i in range(80)}},
            },
            "aggregation_snapshot": {
                "totals": {"canonical_entities": 200},
                "top_recurring_insights": [{"title": str(i)} for i in range(80)],
                "huge": "x" * 10_000,
            },
        },
        "canonical_entity_index": [{"id": str(uuid4()), "title": "x" * 200} for _ in range(80)],
        "draft_external_articles": [
            {"title": "x" * 200, "url": "https://example.com"} for _ in range(80)
        ],
    }

    encoded = _bounded_user_payload_json(payload, max_chars=8_000)

    assert len(encoded) <= 8_000
    assert '"huge"' not in encoded


def test_validation_errors_explain_repair_reasons() -> None:
    errors = _report_data_validation_errors(
        {
            "executive_summary": "Нужно улучшить UX приложения и добавить функцию контроля.",
            "recommendations": [{"insight_fact": ""}],
            "key_findings": [{"text": "Сигнал"}],
        },
        report_language="ru",
    )

    assert "product_or_ux_language_present" in errors
    assert "recommendation_missing_insight_fact" in errors
