"""Tests for batch data readiness diagnostics flags."""

from __future__ import annotations

from app.services.research_batch_dashboard_service import _build_data_readiness_diagnostics


def test_entity_extraction_gap_without_pipelines_running() -> None:
    """No entities after chunking must not imply pipelines are still executing."""
    d = _build_data_readiness_diagnostics(
        interviews_total=2,
        interviews_documents_ready=2,
        transcripts_completed=2,
        chunks_total=10,
        entities_total=0,
        quotes_total=0,
        doc_rows=[],
        audio_scope_count=0,
        base_block={},
    )
    assert d["entity_extraction_gap"] is True
    assert d["pipelines_still_running"] is False
    assert "no_entities" in d["missing_steps"]


def test_pipelines_running_when_docs_not_ready() -> None:
    d = _build_data_readiness_diagnostics(
        interviews_total=2,
        interviews_documents_ready=1,
        transcripts_completed=0,
        chunks_total=0,
        entities_total=0,
        quotes_total=0,
        doc_rows=[{"pipeline": {"phase": "chunked"}}],
        audio_scope_count=0,
        base_block={},
    )
    assert d["pipelines_still_running"] is True
