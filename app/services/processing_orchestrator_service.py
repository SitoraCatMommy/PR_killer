from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus
from app.infrastructure.settings import Settings, get_settings
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.models.text_chunk import TextChunk
from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment
from app.services.chunking_service import ChunkingService
from app.services.openai_semantic_chunking_service import OpenAISemanticChunkingService
from app.services.transcription_service import TranscriptionService

logger = logging.getLogger(__name__)


class ProcessingOrchestratorService:
    """Sync orchestration for Celery: transcribe audio, chunk documents/transcripts."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        chunking: ChunkingService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._chunking = chunking or ChunkingService(
            max_chars=self._settings.chunk_max_chars,
            overlap_chars=self._settings.chunk_overlap_chars,
        )
        self._transcription = TranscriptionService(self._settings)

    def transcribe_audio_source_sync(self, session: Session, source_audio_id: UUID) -> UUID:
        audio = session.get(SourceAudio, source_audio_id)
        if audio is None:
            raise ValueError("source_audio_not_found")

        session.execute(delete(Transcript).where(Transcript.source_audio_id == source_audio_id))
        session.execute(delete(TextChunk).where(TextChunk.source_audio_id == source_audio_id))
        session.flush()

        file_path: Path | None = None
        data = b""
        if audio.original_path:
            path = Path(self._settings.upload_storage_path) / audio.original_path
            if path.is_file():
                data = path.read_bytes()
                file_path = path
            else:
                logger.warning("Audio file missing at %s", path)

        structured = self._transcription.transcribe_structured_sync(
            audio_bytes=data,
            mime_type=audio.mime_type,
            language_hint=audio.language,
            audio_file_path=file_path,
            filename_hint=audio.filename,
        )

        tr = Transcript(
            source_audio_id=source_audio_id,
            full_text=structured.full_text,
            language=structured.language or audio.language,
            status=JobStatus.COMPLETED,
            provider_name=structured.provider_name,
        )
        session.add(tr)
        session.flush()

        for seg in structured.segments:
            session.add(
                TranscriptSegment(
                    transcript_id=tr.id,
                    speaker_label=seg.speaker_label,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                    text=seg.text,
                    confidence_score=seg.confidence_score,
                )
            )
        session.flush()
        return tr.id

    def chunk_source_document_sync(
        self,
        session: Session,
        source_document_id: UUID,
        *,
        strategy: Literal["fixed", "openai"] = "fixed",
    ) -> int:
        doc = session.get(SourceDocument, source_document_id)
        if doc is None:
            raise ValueError("source_document_not_found")
        raw = (doc.raw_text or "").strip()
        if not raw:
            raise ValueError("source_document_no_text")

        session.execute(delete(TextChunk).where(TextChunk.source_document_id == source_document_id))
        session.flush()

        if strategy == "openai":
            semantic = OpenAISemanticChunkingService(self._settings)
            parts = semantic.chunk_full_text(raw)
        else:
            parts = self._chunking.chunk_text(raw)

        meta_base: dict = {"chunking_strategy": strategy}
        if strategy == "openai":
            meta_base["semantic_model"] = self._settings.openai_semantic_chunk_model

        for i, text in enumerate(parts):
            session.add(
                TextChunk(
                    project_id=doc.project_id,
                    source_document_id=source_document_id,
                    source_audio_id=None,
                    transcript_id=None,
                    chunk_index=i,
                    text=text,
                    token_count=None,
                    embedding=None,
                    metadata_json=dict(meta_base),
                )
            )
        session.flush()
        return len(parts)

    def chunk_transcript_sync(
        self,
        session: Session,
        transcript_id: UUID,
        *,
        strategy: Literal["fixed", "openai"] = "fixed",
    ) -> int:
        tr = session.get(Transcript, transcript_id)
        if tr is None:
            raise ValueError("transcript_not_found")

        audio = session.get(SourceAudio, tr.source_audio_id)
        if audio is None:
            raise ValueError("source_audio_not_found")

        session.execute(delete(TextChunk).where(TextChunk.transcript_id == transcript_id))
        session.flush()

        ordered = session.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.start_seconds)
        ).all()
        base = " ".join(s.text for s in ordered) if ordered else tr.full_text
        base = (base or "").strip()
        if not base:
            raise ValueError("transcript_no_text")

        if strategy == "openai":
            semantic = OpenAISemanticChunkingService(self._settings)
            parts = semantic.chunk_full_text(base)
        else:
            parts = self._chunking.chunk_text(base)

        meta_base: dict = {"chunking_strategy": strategy}
        if strategy == "openai":
            meta_base["semantic_model"] = self._settings.openai_semantic_chunk_model

        for i, text in enumerate(parts):
            session.add(
                TextChunk(
                    project_id=audio.project_id,
                    source_document_id=None,
                    source_audio_id=None,
                    transcript_id=transcript_id,
                    chunk_index=i,
                    text=text,
                    token_count=None,
                    embedding=None,
                    metadata_json=dict(meta_base),
                )
            )
        session.flush()
        return len(parts)
