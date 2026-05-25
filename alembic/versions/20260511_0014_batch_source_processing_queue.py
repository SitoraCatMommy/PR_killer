"""Batch source queue: processing status, ordering, timestamps."""

from alembic import op
import sqlalchemy as sa


revision = "20260511_0014"
down_revision = "20260428_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_batch_sources",
        sa.Column(
            "processing_status",
            sa.String(length=32),
            nullable=False,
            server_default="completed",
        ),
    )
    op.add_column(
        "research_batch_sources",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("research_batch_sources", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "research_batch_sources",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "research_batch_sources",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_research_batch_sources_batch_processing",
        "research_batch_sources",
        ["batch_id", "processing_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_research_batch_sources_batch_processing", table_name="research_batch_sources")
    op.drop_column("research_batch_sources", "completed_at")
    op.drop_column("research_batch_sources", "started_at")
    op.drop_column("research_batch_sources", "last_error")
    op.drop_column("research_batch_sources", "sort_order")
    op.drop_column("research_batch_sources", "processing_status")
