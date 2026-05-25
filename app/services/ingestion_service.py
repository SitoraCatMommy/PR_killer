"""Domain research ingestion (sources, files). Celery hooks: `MaterialPipelineDispatcher`."""

from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SourceType
from app.infrastructure.settings import get_settings
from app.infrastructure.storage import FileStorage
from app.services.docx_text_extraction import (
    extract_plain_text_from_docx,
    is_docx_filename_or_mime,
    is_legacy_doc_filename_or_mime,
)
from app.repositories.project_repository import ProjectRepository
from app.repositories.source_audio_repository import SourceAudioRepository
from app.repositories.source_document_repository import SourceDocumentRepository


class IngestionService:
    """Orchestrate project-scoped source ingestion (no transcription / NLP)."""

    _PLAIN_TEXT_MIMES = frozenset(
        {
            "text/plain",
            "text/markdown",
            "application/x-markdown",
        }
    )

    def __init__(
        self,
        session: AsyncSession,
        storage: FileStorage,
        *,
        upload_subdir: str = "research_sources",
    ) -> None:
        self._session = session
        self._storage = storage
        self._upload_subdir = upload_subdir
        self._projects = ProjectRepository(session)
        self._documents = SourceDocumentRepository(session)
        self._audios = SourceAudioRepository(session)

    def _project_prefix(self, project_id: UUID) -> Path:
        return Path(self._upload_subdir) / str(project_id)

    async def ensure_project(self, project_id: UUID) -> None:
        if not await self._projects.exists(project_id):
            raise ValueError("project_not_found")

    def _resolve_document_text(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
    ) -> tuple[str | None, str | None]:
        """Return (raw_text, stored_path). Exactly one of raw_text or stored_path is set."""
        if is_legacy_doc_filename_or_mime(filename, mime_type):
            raise ValueError("doc_format_not_supported_use_docx")
        if is_docx_filename_or_mime(filename, mime_type):
            return extract_plain_text_from_docx(content), None

        ext = Path(filename).suffix.lower()
        is_plain = (mime_type or "").lower() in self._PLAIN_TEXT_MIMES or ext in {
            ".txt",
            ".md",
            ".markdown",
        }
        if is_plain:
            try:
                return content.decode("utf-8"), None
            except UnicodeDecodeError:
                is_plain = False
        return None, None

    async def upload_text_file(
        self,
        project_id: UUID,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
        source_type: SourceType = SourceType.UPLOAD,
        extra_metadata: dict | None = None,
    ):
        await self.ensure_project(project_id)
        meta = dict(extra_metadata or {})
        raw_text, stored_path = self._resolve_document_text(
            filename=filename,
            content=content,
            mime_type=mime_type,
        )
        if raw_text is None and stored_path is None:
            rel = await self._storage.save(
                self._project_prefix(project_id) / "documents",
                filename,
                content,
            )
            stored_path = rel
        doc = await self._documents.create(
            project_id=project_id,
            filename=filename,
            original_path=stored_path,
            mime_type=mime_type,
            source_type=source_type,
            raw_text=raw_text,
            metadata_json=meta,
        )
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def upload_audio_file(
        self,
        project_id: UUID,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
        language: str | None = None,
        source_type: SourceType = SourceType.UPLOAD,
        extra_metadata: dict | None = None,
    ):
        await self.ensure_project(project_id)
        rel = await self._storage.save(
            self._project_prefix(project_id) / "audio",
            filename,
            content,
        )
        meta = dict(extra_metadata or {})
        meta["ingestion_source_type"] = source_type.value
        audio = await self._audios.create(
            project_id=project_id,
            filename=filename,
            original_path=rel,
            mime_type=mime_type,
            language=language,
            metadata_json=meta,
        )
        await self._session.commit()
        await self._session.refresh(audio)
        return audio

    async def upload_audio_file_stream(
        self,
        project_id: UUID,
        *,
        upload_file: UploadFile,
        mime_type: str | None,
        language: str | None = None,
        transcription_language: str | None = None,
        source_type: SourceType = SourceType.UPLOAD,
        extra_metadata: dict | None = None,
    ):
        """Stream-read upload into storage (avoids loading rules that assume ``read()`` once)."""
        await self.ensure_project(project_id)
        max_b = int(get_settings().upload_max_bytes)
        chunks: list[bytes] = []
        total = 0
        while True:
            piece = await upload_file.read(1024 * 1024)
            if not piece:
                break
            total += len(piece)
            if total > max_b:
                raise ValueError("upload_too_large")
            chunks.append(piece)
        content = b"".join(chunks)
        fname = upload_file.filename or "audio"
        meta = dict(extra_metadata or {})
        meta["ingestion_source_type"] = source_type.value
        if transcription_language and str(transcription_language).strip():
            meta["transcription_language"] = str(transcription_language).strip()
        rel = await self._storage.save(
            self._project_prefix(project_id) / "audio",
            fname,
            content,
        )
        audio = await self._audios.create(
            project_id=project_id,
            filename=fname,
            original_path=rel,
            mime_type=mime_type,
            language=language,
            metadata_json=meta,
        )
        await self._session.commit()
        await self._session.refresh(audio)
        return audio

    async def create_raw_text_note(
        self,
        project_id: UUID,
        *,
        title_or_filename: str,
        raw_text: str,
        source_type: SourceType = SourceType.MANUAL,
        extra_metadata: dict | None = None,
    ):
        await self.ensure_project(project_id)
        meta = dict(extra_metadata or {})
        if title_or_filename:
            meta.setdefault("title", title_or_filename)
        doc = await self._documents.create(
            project_id=project_id,
            filename=title_or_filename or "note.txt",
            original_path=None,
            mime_type="text/plain",
            source_type=source_type,
            raw_text=raw_text,
            metadata_json=meta,
        )
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

