from uuid import UUID

from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SourceType
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.repositories.project_repository import ProjectRepository
from app.repositories.research_entity_repository import ExtractedEntityRepository
from app.repositories.source_audio_repository import SourceAudioRepository
from app.repositories.source_document_repository import SourceDocumentRepository
from app.repositories.text_chunk_repository import TextChunkRepository
from app.repositories.transcript_repository import TranscriptRepository
from app.schemas.pagination import PaginatedMeta
from app.schemas.research_chunk import TextChunkRead
from app.schemas.research_source import (
    AudioSourceListItem,
    DocumentSourceListItem,
    SourceAudioDetailRead,
    SourceAudioRead,
    SourceDocumentDetailRead,
    SourceDocumentRead,
    UnifiedSourcesResponse,
)
from app.schemas.research_transcript import TranscriptRead, TranscriptSegmentRead


def stmt_unified_sources_page(project_id: UUID, *, offset: int, limit: int):
    docs = (
        select(
            literal("document").label("source_kind"),
            SourceDocument.id.label("id"),
            SourceDocument.project_id.label("project_id"),
            SourceDocument.filename.label("filename"),
            SourceDocument.mime_type.label("mime_type"),
            SourceDocument.source_type.label("source_type"),
            literal(None).label("language"),
            SourceDocument.created_at.label("created_at"),
        )
        .where(SourceDocument.project_id == project_id)
    )
    audios = (
        select(
            literal("audio").label("source_kind"),
            SourceAudio.id.label("id"),
            SourceAudio.project_id.label("project_id"),
            SourceAudio.filename.label("filename"),
            SourceAudio.mime_type.label("mime_type"),
            literal(None).label("source_type"),
            SourceAudio.language.label("language"),
            SourceAudio.created_at.label("created_at"),
        )
        .where(SourceAudio.project_id == project_id)
    )
    sources = union_all(docs, audios).subquery()
    return (
        select(sources)
        .order_by(sources.c.created_at.desc(), sources.c.id.desc())
        .offset(offset)
        .limit(limit)
    )


def _coerce_source_type(value: object) -> SourceType:
    if isinstance(value, SourceType):
        return value
    if isinstance(value, str):
        try:
            return SourceType(value)
        except ValueError:
            return SourceType[value]
    raise TypeError(f"Unexpected source_type value: {value!r}")


class SourceQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)
        self._documents = SourceDocumentRepository(session)
        self._audios = SourceAudioRepository(session)
        self._transcripts = TranscriptRepository(session)
        self._chunks = TextChunkRepository(session)
        self._entities = ExtractedEntityRepository(session)

    async def list_unified_sources(
        self,
        project_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> UnifiedSourcesResponse:
        if not await self._projects.exists(project_id):
            raise ValueError("project_not_found")
        rows_result = await self._session.execute(
            stmt_unified_sources_page(project_id, offset=offset, limit=limit)
        )
        doc_total = await self._documents.count_by_project(project_id)
        audio_total = await self._audios.count_by_project(project_id)
        merged: list[DocumentSourceListItem | AudioSourceListItem] = []
        for row in rows_result.mappings():
            if row["source_kind"] == "document":
                merged.append(
                    DocumentSourceListItem(
                        source_kind="document",
                        id=row["id"],
                        project_id=row["project_id"],
                        filename=row["filename"],
                        mime_type=row["mime_type"],
                        source_type=_coerce_source_type(row["source_type"]),
                        created_at=row["created_at"],
                    )
                )
            else:
                merged.append(
                    AudioSourceListItem(
                        source_kind="audio",
                        id=row["id"],
                        project_id=row["project_id"],
                        filename=row["filename"],
                        mime_type=row["mime_type"],
                        language=row["language"],
                        created_at=row["created_at"],
                    )
                )
        return UnifiedSourcesResponse(
            items=merged,
            meta=PaginatedMeta(total=doc_total + audio_total, limit=limit, offset=offset),
        )

    async def get_document_detail(self, document_id: UUID) -> SourceDocumentDetailRead | None:
        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            return None
        base = SourceDocumentRead.model_validate(doc)
        chunks = await self._chunks.count_for_document(document_id)
        ents = await self._entities.count_for_document(document_id)
        return SourceDocumentDetailRead(
            **base.model_dump(),
            transcript=None,
            transcript_segments_count=0,
            text_chunks_count=chunks,
            extracted_entities_count=ents,
        )

    async def list_document_chunks(self, document_id: UUID) -> list[TextChunkRead] | None:
        """Return ordered chunks for a document, or None if document does not exist."""
        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            return None
        rows = await self._chunks.list_for_document_ordered(document_id)
        return [TextChunkRead.model_validate(r) for r in rows]

    async def get_audio_detail(self, audio_id: UUID) -> SourceAudioDetailRead | None:
        audio = await self._audios.get_by_id(audio_id)
        if audio is None:
            return None
        base = SourceAudioRead.model_validate(audio)
        tr = await self._transcripts.get_latest_for_audio(audio_id)
        if tr:
            tr_read = TranscriptRead.model_validate(tr)
            ent_n = await self._entities.count_for_transcript(tr.id)
            tr_read = tr_read.model_copy(update={"extracted_entities_count": ent_n})
        else:
            tr_read = None
        seg_count = await self._transcripts.count_segments(tr.id) if tr else 0
        seg_sample = (
            [TranscriptSegmentRead.model_validate(s) for s in await self._transcripts.list_segments_preview(tr.id)]
            if tr
            else []
        )
        chunks = await self._chunks.count_for_audio(audio_id)
        ents = await self._entities.count_for_audio(audio_id)
        return SourceAudioDetailRead(
            **base.model_dump(),
            transcript=tr_read,
            transcript_segments_count=seg_count,
            transcript_segments_sample=seg_sample,
            text_chunks_count=chunks,
            extracted_entities_count=ents,
        )
