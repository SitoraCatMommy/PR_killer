from __future__ import annotations

from uuid import uuid4

from app.services.pr_lexicon_signals import build_pr_lexicon_signals_from_chunks


def test_pr_lexicon_phrase_and_quote() -> None:
    cid = uuid4()
    tid = uuid4()
    chunks = [
        {
            "id": cid,
            "text": "Я не доверяю этому банку после блокировки карты",
            "transcript_id": tid,
            "source_document_id": None,
            "source_audio_id": None,
        }
    ]
    out = build_pr_lexicon_signals_from_chunks(chunks, interview_count=3, brand_tokens=["Click"])
    assert out["has_signals"] is True
    flat = out["signals_flat"]
    terms = {x["term"] for x in flat}
    assert "не доверяю" in terms or any("не доверяю" in x["term"] for x in flat)
    hit = next(x for x in flat if "не доверяю" in x["term"] or x["term"] == "не доверяю")
    assert hit["count"] >= 1
    assert hit["interview_coverage"] >= 1
    assert hit["example_quotes"]


def test_pr_lexicon_filters_fillers() -> None:
    cid = uuid4()
    chunks = [
        {
            "id": cid,
            "text": "ну типа вот это самое короче человек люди",
            "transcript_id": None,
            "source_document_id": uuid4(),
            "source_audio_id": None,
        }
    ]
    out = build_pr_lexicon_signals_from_chunks(chunks, interview_count=2, brand_tokens=[])
    assert out["has_signals"] is False


def test_pr_lexicon_brand_token() -> None:
    cid = uuid4()
    chunks = [
        {
            "id": cid,
            "text": "Мне нравится Click в приложении каждый день",
            "transcript_id": None,
            "source_document_id": uuid4(),
            "source_audio_id": None,
        }
    ]
    out = build_pr_lexicon_signals_from_chunks(chunks, interview_count=1, brand_tokens=["Click"])
    assert out["has_signals"] is True
    assert any(x["term"] == "click" and x["category"] == "brand" for x in out["signals_flat"])
