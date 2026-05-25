"""CustDev PR pipeline: interview units, batch multi-interview mode, document pipeline state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260428_0013"
down_revision = "20260427_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_batches",
        sa.Column(
            "single_file_multi_interview_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "source_documents",
        sa.Column(
            "pipeline_state_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_table(
        "interview_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_index", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=512), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("language_confidence", sa.Float(), nullable=True),
        sa.Column("split_method", sa.String(length=32), nullable=False, server_default="heuristic"),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_interview_units_project", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_interview_units_source_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_units"),
        sa.UniqueConstraint(
            "source_document_id",
            "unit_index",
            name="uq_interview_units_document_unit_index",
        ),
    )
    op.create_index("ix_interview_units_project_id", "interview_units", ["project_id"], unique=False)
    op.create_index(
        "ix_interview_units_source_document_id",
        "interview_units",
        ["source_document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interview_units_source_document_id", table_name="interview_units")
    op.drop_index("ix_interview_units_project_id", table_name="interview_units")
    op.drop_table("interview_units")
    op.drop_column("source_documents", "pipeline_state_json")
    op.drop_column("research_batches", "single_file_multi_interview_mode")
