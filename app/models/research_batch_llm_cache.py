import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_batch import ResearchBatch


class ResearchBatchLlmCache(Base, UUIDPrimaryKeyMixin):
    """Cached JSON payloads for expensive batch LLM endpoints (portrait, PR strategy)."""

    __tablename__ = "research_batch_llm_cache"
    __table_args__ = (
        Index("ix_research_batch_llm_cache_batch_id", "batch_id"),
        Index("ix_research_batch_llm_cache_batch_kind", "batch_id", "cache_kind"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    cache_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(767), nullable=False, unique=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    batch: Mapped["ResearchBatch"] = relationship(back_populates="llm_caches")
