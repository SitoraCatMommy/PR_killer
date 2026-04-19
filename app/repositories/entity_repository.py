import hashlib
import uuid
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntityKind
from app.models.material_extracted_entity import MaterialExtractedEntity


def entity_fingerprint(
    kind: EntityKind,
    label: str,
    normalized_value: str | None,
    span_start: int | None,
    span_end: int | None,
) -> str:
    raw = f"{kind}|{label}|{normalized_value or ''}|{span_start}|{span_end}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_for_material(
        self,
        material_id: UUID,
        entities: list[dict],
    ) -> int:
        """Insert entities; skip duplicates per (material_id, fingerprint). Returns inserted count."""
        inserted = 0
        for e in entities:
            kind = EntityKind(e["kind"])
            label = str(e["label"])
            nv = e.get("normalized_value")
            ss = e.get("span_start")
            se = e.get("span_end")
            fp = entity_fingerprint(kind, label, nv, ss, se)
            payload = dict(e.get("payload") or {})
            stmt = (
                insert(MaterialExtractedEntity)
                .values(
                    id=uuid.uuid4(),
                    material_id=material_id,
                    kind=kind,
                    label=label,
                    normalized_value=nv,
                    span_start=ss,
                    span_end=se,
                    payload=payload,
                    fingerprint=fp,
                )
                .on_conflict_do_nothing(constraint="uq_entity_material_fingerprint")
            )
            res = await self._session.execute(stmt)
            if res.rowcount:
                inserted += 1
        await self._session.flush()
        return inserted

    async def delete_for_material(self, material_id: UUID) -> None:
        await self._session.execute(
            delete(MaterialExtractedEntity).where(MaterialExtractedEntity.material_id == material_id)
        )
        await self._session.flush()

    async def list_for_material(self, material_id: UUID) -> list[MaterialExtractedEntity]:
        stmt = select(MaterialExtractedEntity).where(MaterialExtractedEntity.material_id == material_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
