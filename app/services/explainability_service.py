"""Lightweight explainability signals derived from batch portrait context (no new analytics)."""

from __future__ import annotations

from typing import Any

_MAX_SAMPLE_QUOTE_CHARS = 420
_MAX_SAMPLE_QUOTES = 8


def segment_coverage_from_snapshot(audience_snapshot: dict[str, Any], interview_total: int) -> dict[str, Any]:
    """Per-dimension counts already present in dashboard snapshot; adds interview total."""
    out: dict[str, Any] = {"interview_count": interview_total}
    for key in ("gender", "age_range", "segments", "language", "city", "interview_type", "source"):
        block = audience_snapshot.get(key)
        if isinstance(block, dict) and block:
            out[key] = block
    return out


def explainability_bundle(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    evidence_count: grounded snippets (quotes + distilled insights).
    segment_coverage: audience snapshot slices with counts.
    sample_quotes: short list of representative quote lines for API consumers.
    """
    quotes = ctx.get("quotes") or []
    if not isinstance(quotes, list):
        quotes = []
    top_insights = ctx.get("top_insights") or []
    if not isinstance(top_insights, list):
        top_insights = []

    evidence_count = len(quotes) + len(top_insights)

    snap = ctx.get("audience_snapshot")
    if not isinstance(snap, dict):
        snap = {}
    interview_total = int(snap.get("interview_count") or ctx.get("interview_count") or 0)
    segment_coverage = segment_coverage_from_snapshot(snap, interview_total)

    sample_quotes: list[dict[str, str]] = []
    for q in quotes[:_MAX_SAMPLE_QUOTES]:
        if not isinstance(q, dict):
            continue
        text = str(q.get("text") or "").strip()
        if not text:
            continue
        item: dict[str, Any] = {
            "type": str(q.get("type") or ""),
            "title": str(q.get("title") or ""),
            "text": text[:_MAX_SAMPLE_QUOTE_CHARS],
        }
        for k in (
            "entity_id",
            "source_document_id",
            "source_audio_id",
            "transcript_id",
            "chunk_id",
        ):
            v = q.get(k)
            if v:
                item[k] = str(v)
        sample_quotes.append(item)

    return {
        "evidence_count": evidence_count,
        "segment_coverage": segment_coverage,
        "sample_quotes": sample_quotes,
    }
