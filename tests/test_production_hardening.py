from __future__ import annotations

from io import BytesIO
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.dialects import postgresql

from app.api.upload_utils import read_upload_file_with_limit
from app.infrastructure.settings import Settings
from app.infrastructure.storage.local import safe_upload_filename
from app.repositories.text_chunk_repository import stmt_chunks_for_document_ordered
from app.services.source_query_service import stmt_unified_sources_page


def _postgres_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_chunk_list_statement_does_not_select_embeddings() -> None:
    sql = _postgres_sql(stmt_chunks_for_document_ordered(uuid4()))

    assert "text_chunks.embedding" not in sql
    assert "text_chunks.metadata_json" not in sql
    assert "text_chunks.text" in sql


def test_unified_sources_page_statement_omits_raw_text() -> None:
    sql = _postgres_sql(stmt_unified_sources_page(uuid4(), offset=20, limit=10))

    assert "source_documents.raw_text" not in sql
    assert "source_documents.filename" in sql
    assert "LIMIT" in sql
    assert "OFFSET" in sql


@pytest.mark.asyncio
async def test_read_upload_file_with_limit_rejects_oversized_body() -> None:
    upload = UploadFile(file=BytesIO(b"abcdef"), filename="example.txt")

    with pytest.raises(HTTPException) as exc:
        await read_upload_file_with_limit(upload, max_bytes=5, chunk_bytes=2)

    assert exc.value.status_code == 413
    assert exc.value.detail["code"] == "upload_too_large"


@pytest.mark.asyncio
async def test_read_upload_file_with_limit_accepts_body_at_limit() -> None:
    upload = UploadFile(file=BytesIO(b"abcde"), filename="example.txt")

    data = await read_upload_file_with_limit(upload, max_bytes=5, chunk_bytes=2)

    assert data == b"abcde"


def test_safe_upload_filename_strips_path_segments() -> None:
    assert safe_upload_filename("../secret.txt") == "secret.txt"
    assert safe_upload_filename("nested/folder/audio.wav") == "audio.wav"
    assert safe_upload_filename("..") == "upload.bin"


def test_wildcard_cors_disables_credentials_header() -> None:
    assert Settings(CORS_ORIGINS="*").cors_allow_credentials is False
    assert Settings(CORS_ORIGINS="https://example.com").cors_allow_credentials is True
