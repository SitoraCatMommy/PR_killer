"""Research batches (multi-source studies) and optional report.batch_id."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421_0006"
down_revision = "20260420_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_research_batches_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_batches"),
    )
    op.create_index(
        "ix_research_batches_project_id_created_at",
        "research_batches",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "research_batch_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_audio_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(source_document_id IS NOT NULL)::int + (source_audio_id IS NOT NULL)::int = 1",
            name="ck_research_batch_sources_one_surface",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["research_batches.id"],
            name="fk_research_batch_sources_batch_id_research_batches",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_research_batch_sources_source_document_id_source_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_audio_id"],
            ["source_audios.id"],
            name="fk_research_batch_sources_source_audio_id_source_audios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_batch_sources"),
    )
    op.create_index(
        "ix_research_batch_sources_batch_id",
        "research_batch_sources",
        ["batch_id"],
        unique=False,
    )

    op.add_column(
        "research_reports",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_research_reports_batch_id_research_batches",
        "research_reports",
        "research_batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_research_reports_batch_id_updated_at",
        "research_reports",
        ["batch_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_research_reports_batch_id_updated_at", table_name="research_reports")
    op.drop_constraint("fk_research_reports_batch_id_research_batches", "research_reports", type_="foreignkey")
    op.drop_column("research_reports", "batch_id")

    op.drop_index("ix_research_batch_sources_batch_id", table_name="research_batch_sources")
    op.drop_table("research_batch_sources")

    op.drop_index("ix_research_batches_project_id_created_at", table_name="research_batches")
    op.drop_table("research_batches")
