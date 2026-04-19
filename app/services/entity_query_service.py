from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntityType
from app.domain.pr_workspace import DEFAULT_LIST_EXCLUDED_ENTITY_TYPES
from app.repositories.project_repository import ProjectRepository
from app.repositories.research_entity_repository import ExtractedEntityRepository
from app.schemas.pagination import PaginatedMeta
from app.schemas.research_entity import EntityListResponse, ExtractedEntityRead
from app.services.pr_entity_enrichment import pr_fields_for_entity


class EntityQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._entities = ExtractedEntityRepository(session)
        self._projects = ProjectRepository(session)

    async def list_for_project(
        self,
        project_id: UUID,
        *,
        entity_type: EntityType | None,
        min_confidence: float | None,
        source_document_id: UUID | None,
        source_audio_id: UUID | None,
        transcript_id: UUID | None,
        offset: int,
        limit: int,
        include_all_types: bool = False,
    ) -> EntityListResponse:
        if not await self._projects.exists(project_id):
            raise ValueError("project_not_found")
        exclude: frozenset[EntityType] | None = None
        if not include_all_types and entity_type is None:
            exclude = DEFAULT_LIST_EXCLUDED_ENTITY_TYPES
        rows, total = await self._entities.list_for_project(
            project_id,
            entity_type=entity_type,
            min_confidence=min_confidence,
            source_document_id=source_document_id,
            source_audio_id=source_audio_id,
            transcript_id=transcript_id,
            offset=offset,
            limit=limit,
            exclude_entity_types=exclude,
        )
        items: list[ExtractedEntityRead] = []
        for r in rows:
            base = ExtractedEntityRead.model_validate(r)
            pi, mg = pr_fields_for_entity(r)
            items.append(base.model_copy(update={"pr_implication": pi, "messaging_guidance": mg}))
        return EntityListResponse(
            items=items,
            meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        )
