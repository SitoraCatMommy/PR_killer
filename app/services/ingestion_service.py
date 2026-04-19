"""Domain research ingestion (sources, files). Celery hooks: `MaterialPipelineDispatcher`."""

from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SourceType
from app.infrastructure.storage import FileStorage
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
        ext = Path(filename).suffix.lower()
        is_plain = (mime_type or "").lower() in self._PLAIN_TEXT_MIMES or ext in {".txt", ".md", ".markdown"}
        raw_text: str | None = None
        stored_path: str | None = None
        if is_plain:
            try:
                raw_text = content.decode("utf-8")
            except UnicodeDecodeError:
                is_plain = False
        if not is_plain:
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

