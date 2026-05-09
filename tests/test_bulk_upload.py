from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Response, UploadFile, status

from app.api.routes.research_sources import upload_text_sources_bulk
from app.api.v1.materials import ingest_audio_bulk
from app.infrastructure.settings import Settings


def _upload(filename: str, data: bytes) -> UploadFile:
    return UploadFile(file=BytesIO(data), filename=filename)


class FakeMaterialService:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []
        self.titles: list[str | None] = []

    async def ingest_audio(self, **kwargs: object) -> tuple[UUID, str]:
        material_id = uuid4()
        self.enqueued.append(material_id)
        self.titles.append(kwargs.get("title") if isinstance(kwargs.get("title"), str) else None)
        return material_id, f"task-{len(self.enqueued)}"


@pytest.mark.asyncio
async def test_bulk_material_audio_upload_queues_each_file(tmp_path) -> None:
    svc = FakeMaterialService()
    response = Response()
    settings = Settings(UPLOAD_STORAGE_PATH=str(tmp_path), UPLOAD_MAX_BYTES=20, UPLOAD_MAX_FILES=5)

    result = await ingest_audio_bulk(
        response,
        svc,
        settings,
        [_upload("one.wav", b"111"), _upload("two.wav", b"222")],
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert result.succeeded == 2
    assert result.failed == 0
    assert [item.task_id for item in result.items] == ["task-1", "task-2"]
    assert len(svc.enqueued) == 2
    assert svc.titles == ["one", "two"]


@pytest.mark.asyncio
async def test_bulk_material_audio_upload_reports_per_file_size_errors(tmp_path) -> None:
    svc = FakeMaterialService()
    response = Response()
    settings = Settings(UPLOAD_STORAGE_PATH=str(tmp_path), UPLOAD_MAX_BYTES=3, UPLOAD_MAX_FILES=5)

    result = await ingest_audio_bulk(
        response,
        svc,
        settings,
        [_upload("ok.wav", b"123"), _upload("large.wav", b"1234")],
    )

    assert response.status_code == status.HTTP_207_MULTI_STATUS
    assert result.succeeded == 1
    assert result.failed == 1
    assert len(svc.enqueued) == 1
    assert result.items[1].filename == "large.wav"
    assert result.items[1].error_code == "upload_too_large"


class FakeProjectService:
    async def get(self, _project_id: UUID) -> object:
        return object()


class FakeIngestionService:
    def __init__(self) -> None:
        self.created: list[UUID] = []

    async def upload_text_file(self, *args: object, **kwargs: object) -> object:
        document_id = uuid4()
        self.created.append(document_id)
        return SimpleNamespace(id=document_id)


@pytest.mark.asyncio
async def test_bulk_project_text_upload_creates_each_source() -> None:
    ingestion = FakeIngestionService()
    response = Response()
    settings = Settings(UPLOAD_MAX_BYTES=20, UPLOAD_MAX_FILES=5)

    result = await upload_text_sources_bulk(
        uuid4(),
        response,
        ingestion,
        FakeProjectService(),
        settings,
        [_upload("a.txt", b"a"), _upload("b.txt", b"b")],
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert result.succeeded == 2
    assert result.failed == 0
    assert len(ingestion.created) == 2
    assert [item.source_kind for item in result.items] == ["document", "document"]
