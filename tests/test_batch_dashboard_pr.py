from datetime import date, datetime, timezone
from types import SimpleNamespace
from app.services.batch_dashboard_pr import (
    entity_matches_date_filter,
    parse_iso_date,
    tokenize_corpus,
)


def test_parse_iso_date() -> None:
    assert parse_iso_date("2026-04-01") == date(2026, 4, 1)
    assert parse_iso_date(None) is None


def test_tokenize_stopwords() -> None:
    text = "the quick brown fox jumps over the lazy dog"
    raw = tokenize_corpus(text, limit=20, apply_stopwords=False)
    words = [w for w, _ in raw]
    assert "the" in words
    sw = tokenize_corpus(text, limit=20, apply_stopwords=True)
    sw_words = [w for w, _ in sw]
    assert "the" not in sw_words


def test_entity_matches_date_filter() -> None:
    e = SimpleNamespace(created_at=datetime(2026, 4, 10, tzinfo=timezone.utc))
    assert entity_matches_date_filter(e, {"date": "2026-04-10"}, date(2026, 4, 1), date(2026, 4, 30)) is True
    assert entity_matches_date_filter(e, {"date": "2026-04-10"}, date(2026, 5, 1), None) is False
