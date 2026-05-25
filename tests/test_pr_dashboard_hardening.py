"""PR dashboard contract: filters, trend (real timeline only), taxonomy rows, .env.example hygiene."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes.research_batches import _dashboard_build_kwargs
from app.domain.enums import EntityType
from app.services.batch_dashboard_pr import EMPTY_TIMELINE_REAL, pr_signal_tag_integrity, timeline_series_real
from app.services.custdev_report_bundle import build_trend_dashboard
from app.services.research_batch_dashboard_service import _traceability_rows


def test_dashboard_build_kwargs_parity_with_export() -> None:
    k = _dashboard_build_kwargs(
        group_by="gender",
        segment_key="female",
        date_from="2024-01-15",
        date_to="2024-06-01",
        stopwords=True,
        compare_segment_a="a",
        compare_segment_b="b",
    )
    assert k == {
        "group_by": "gender",
        "segment_key": "female",
        "date_from": "2024-01-15",
        "date_to": "2024-06-01",
        "stopwords": True,
        "compare_segment_a": "a",
        "compare_segment_b": "b",
    }


def test_env_example_no_realistic_secret_tokens() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / ".env.example").read_text(encoding="utf-8")
    assert "sk-proj-" not in text, ".env.example must not ship sk-proj-* style keys"
    assert "AIzaSy" not in text, ".env.example must not ship Gemini-style API keys"
    for line in text.splitlines():
        ls = line.strip()
        if ls.startswith("#") or "=" not in ls:
            continue
        key, _, val = ls.partition("=")
        val = val.strip()
        if key.strip().upper().endswith("_API_KEY") and val and not val.startswith("${"):
            assert "REPLACE" in val or "your" in val.lower() or "changeme" in val.lower(), (
                f"{key.strip()} should use an obvious placeholder, not a live-looking secret"
            )


def test_trend_dashboard_empty_no_heuristic_points() -> None:
    out = build_trend_dashboard({"timeline_series_real": dict(EMPTY_TIMELINE_REAL)})
    assert out["series"] == []
    assert out["diagnostics"] == "empty_timeline"
    assert "Heuristic" not in (out.get("notes") or "")


def test_trend_dashboard_with_real_buckets() -> None:
    tl = {
        "note": "test",
        "series": [
            {
                "period": "2025-W01",
                "sentiment_balance": 2,
                "positive_signals": 3,
                "negative_signals": 1,
                "risk_volume": 4,
                "theme_volume": 2,
            },
            {
                "period": "2025-W02",
                "sentiment_balance": -1,
                "positive_signals": 1,
                "negative_signals": 2,
                "risk_volume": 8,
                "theme_volume": 1,
            },
        ],
        "emerging": ["t1"],
        "fading": ["t0"],
    }
    out = build_trend_dashboard({"timeline_series_real": tl})
    assert len(out["series"]) == 2
    assert out["series"][0]["period"] == "2025-W01"
    assert 0 <= out["series"][0]["sentiment_score"] <= 100
    assert 0 <= out["series"][0]["risk_index"] <= 100
    assert out["series"][1]["risk_index"] == 100
    assert out["emerging_themes"] == ["t1"]
    assert out.get("diagnostics") is None


def test_traceability_row_pr_signal_vs_legacy_entity_type() -> None:
    pid = uuid4()
    did = uuid4()
    cid = uuid4()
    eid = uuid4()
    ent = SimpleNamespace(
        id=eid,
        project_id=pid,
        entity_type=EntityType.RISK,
        title="Price concern",
        content="They said price is too high",
        evidence_json={},
        tags_json={"pr_signal": "risk_signal"},
        source_document_id=did,
        source_audio_id=None,
        transcript_id=None,
        chunk_id=cid,
    )
    rows = _traceability_rows([ent], {}, {}, {}, limit=10)
    assert len(rows) == 1
    assert rows[0]["pr_signal_type"] == "risk_signal"
    assert rows[0]["entity_type"] == "risk"


def test_pr_signal_tag_integrity_detects_mismatch() -> None:
    pid = uuid4()
    did = uuid4()
    cid = uuid4()
    eid = uuid4()
    bad = SimpleNamespace(
        id=eid,
        project_id=pid,
        entity_type=EntityType.TOPIC,
        title="x",
        content="y",
        evidence_json={},
        tags_json={"pr_signal": "risk_signal"},
        source_document_id=did,
        source_audio_id=None,
        transcript_id=None,
        chunk_id=cid,
    )
    li = pr_signal_tag_integrity([bad])
    assert li["explicit_pr_signal_tag_count"] == 1
    assert li["entity_type_mismatch_vs_pr_signal"] == 1
    assert li["mixed_integrity_warning"] is True


def test_timeline_series_real_empty_shape() -> None:
    assert timeline_series_real([], lambda _e: {}) == EMPTY_TIMELINE_REAL
