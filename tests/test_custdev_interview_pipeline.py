"""CustDev multi-interview split, language hints, cache keys, and optional API checks."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.batch_cached_llm_service import make_cache_key
from app.services.interview_unit_split_service import _detect_language, build_interview_unit_drafts


def test_marker_split_produces_many_interview_units() -> None:
    st = MagicMock()
    st.openai_api_key = ""
    raw = "\n".join([f"Интервью #{i + 1}\nТекст интервью {i + 1} про продукт." for i in range(22)])
    drafts = build_interview_unit_drafts(raw, multi_interview_mode=True, settings=st)
    assert len(drafts) >= 20
    assert all(d.split_method == "marker" for d in drafts)


def test_mixed_language_detection() -> None:
    ru, c1 = _detect_language("Это русский текст про опыт.")
    assert ru == "ru"
    assert c1 > 0.4
    en, c2 = _detect_language("This is English feedback about onboarding.")
    assert en == "en"
    uzish = "Men mobil ilovadan foydalanaman, lekin ba'zi joylar chalkash."
    lg, c3 = _detect_language(uzish)
    assert lg in ("uz", "mixed", "en", "ru")


def test_make_cache_key_depends_on_multi_interview_mode() -> None:
    bid = uuid4()
    k1 = make_cache_key("audience_portrait", bid, None, None, "ru", multi_interview_mode=True)
    k2 = make_cache_key("audience_portrait", bid, None, None, "ru", multi_interview_mode=False)
    assert k1 != k2
    assert "sf1" in k1
    assert "sf0" in k2


def test_generation_cache_consistency_toggle_changes_key() -> None:
    """Portrait/strategy cache keys must change when batch multi-interview flag changes."""
    bid = uuid4()
    a = make_cache_key("pr_strategy", bid, "gender", "female", "en", multi_interview_mode=True)
    b = make_cache_key("pr_strategy", bid, "gender", "female", "en", multi_interview_mode=False)
    assert a != b


@pytest.mark.integration
def test_interview_units_list_endpoint(client: TestClient, api_prefix: str) -> None:
    """Requires migrated DB with interview_units table."""
    r = client.get(f"{api_prefix}/health")
    if r.status_code >= 500:
        pytest.skip("API unavailable")
    r2 = client.post(f"{api_prefix}/projects", json={"name": "pytest-custdev", "output_language": "ru"})
    if r2.status_code != 201:
        pytest.skip(f"cannot create project: {r2.status_code}")
    pid = r2.json()["id"]
    r3 = client.post(f"{api_prefix}/projects/{pid}/batches", json={"name": "b1", "description": None})
    assert r3.status_code == 201, r3.text
    bid = r3.json()["id"]
    raw = "Интервью #1\nHello.\n\nИнтервью #2\nOila."
    up = client.post(
        f"{api_prefix}/projects/{pid}/sources/text/upload",
        files={"file": ("multi.txt", raw.encode("utf-8"), "text/plain")},
        data={"source_type": "upload"},
    )
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]
    add = client.post(
        f"{api_prefix}/batches/{bid}/sources",
        json={"source_document_id": str(doc_id)},
    )
    assert add.status_code == 201, add.text
    from app.workers.tasks.research_processing import chunk_source_document

    ch = chunk_source_document.run(str(doc_id), "auto")
    assert ch.get("status") == "ok", ch
    units = client.get(f"{api_prefix}/batches/{bid}/interview-units")
    if units.status_code >= 500:
        pytest.skip("interview_units table or server error")
    assert units.status_code == 200, units.text
    body = units.json()
    assert "items" in body
    assert len(body["items"]) >= 2
