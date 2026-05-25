"""LLM result cache for batch audience portrait and PR strategy."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260421_0007"
down_revision = "20260421_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_batch_llm_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cache_kind", sa.String(length=32), nullable=False),
        sa.Column("cache_key", sa.String(length=767), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["research_batches.id"],
            name="fk_research_batch_llm_cache_batch_id_research_batches",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_batch_llm_cache"),
        sa.UniqueConstraint("cache_key", name="uq_research_batch_llm_cache_cache_key"),
    )
    op.create_index(
        "ix_research_batch_llm_cache_batch_id",
        "research_batch_llm_cache",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_batch_llm_cache_batch_kind",
        "research_batch_llm_cache",
        ["batch_id", "cache_kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_research_batch_llm_cache_batch_kind", table_name="research_batch_llm_cache")
    op.drop_index("ix_research_batch_llm_cache_batch_id", table_name="research_batch_llm_cache")
    op.drop_table("research_batch_llm_cache")
