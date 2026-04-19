"""step2 research domain schema

Revision ID: 20250403_0002
Revises: 20250403_0001
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250403_0002"
down_revision: Union[str, Sequence[str], None] = "20250403_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_name", "projects", ["name"], unique=False)

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=1024), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_src_doc_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_documents"),
    )
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"], unique=False)
    op.create_index("ix_source_documents_mime_type", "source_documents", ["mime_type"], unique=False)
    op.create_index("ix_source_documents_source_type", "source_documents", ["source_type"], unique=False)
    op.create_index(
        "ix_source_documents_project_id_created_at",
        "source_documents",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "source_audios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=1024), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(12, 3), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_src_aud_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_audios"),
    )
    op.create_index("ix_source_audios_project_id", "source_audios", ["project_id"], unique=False)
    op.create_index("ix_source_audios_mime_type", "source_audios", ["mime_type"], unique=False)
    op.create_index("ix_source_audios_language", "source_audios", ["language"], unique=False)
    op.create_index(
        "ix_source_audios_project_id_created_at",
        "source_audios",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_audio_id", sa.Uuid(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_audio_id"],
            ["source_audios.id"],
            name="fk_trn_src_aud",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transcripts"),
    )
    op.create_index("ix_transcripts_source_audio_id", "transcripts", ["source_audio_id"], unique=False)
    op.create_index("ix_transcripts_language", "transcripts", ["language"], unique=False)
    op.create_index("ix_transcripts_status", "transcripts", ["status"], unique=False)

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column("start_seconds", sa.Numeric(12, 3), nullable=False),
        sa.Column("end_seconds", sa.Numeric(12, 3), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_trn_seg_trn",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transcript_segments"),
    )
    op.create_index("ix_transcript_segments_transcript_id", "transcript_segments", ["transcript_id"], unique=False)
    op.create_index(
        "ix_transcript_segments_speaker_label",
        "transcript_segments",
        ["speaker_label"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_transcript_id_start",
        "transcript_segments",
        ["transcript_id", "start_seconds"],
        unique=False,
    )

    op.create_table(
        "text_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_audio_id", sa.Uuid(), nullable=True),
        sa.Column("transcript_id", sa.Uuid(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(source_document_id IS NOT NULL)::int + (source_audio_id IS NOT NULL)::int + "
            "(transcript_id IS NOT NULL)::int = 1",
            name="ck_text_chunks_exactly_one_source",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_txtch_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_txtch_src_doc",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_audio_id"],
            ["source_audios.id"],
            name="fk_txtch_src_aud",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_txtch_trn",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_text_chunks"),
    )
    op.create_index("ix_text_chunks_project_id", "text_chunks", ["project_id"], unique=False)
    op.create_index(
        "ix_text_chunks_project_id_created_at",
        "text_chunks",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_text_chunks_transcript_id", "text_chunks", ["transcript_id"], unique=False)
    op.create_index("ix_text_chunks_source_document_id", "text_chunks", ["source_document_id"], unique=False)
    op.create_index("ix_text_chunks_source_audio_id", "text_chunks", ["source_audio_id"], unique=False)
    op.create_index(
        "uq_text_chunks_project_document_chunk_index",
        "text_chunks",
        ["project_id", "source_document_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("source_document_id IS NOT NULL"),
    )
    op.create_index(
        "uq_text_chunks_project_audio_chunk_index",
        "text_chunks",
        ["project_id", "source_audio_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("source_audio_id IS NOT NULL"),
    )
    op.create_index(
        "uq_text_chunks_transcript_chunk_index",
        "text_chunks",
        ["transcript_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("transcript_id IS NOT NULL"),
    )

    op.create_table(
        "research_extracted_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_audio_id", sa.Uuid(), nullable=True),
        sa.Column("transcript_id", sa.Uuid(), nullable=True),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column(
            "tags_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("canonical_entity_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(source_document_id IS NOT NULL)::int + (source_audio_id IS NOT NULL)::int + "
            "(transcript_id IS NOT NULL)::int = 1",
            name="ck_research_entities_exactly_one_source",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_re_ent_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_re_ent_src_doc",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_audio_id"],
            ["source_audios.id"],
            name="fk_re_ent_src_aud",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_re_ent_trn",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["text_chunks.id"],
            name="fk_re_ent_chunk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_entity_id"],
            ["research_extracted_entities.id"],
            name="fk_re_ent_canonical",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_extracted_entities"),
    )
    op.create_index("ix_research_extracted_entities_project_id", "research_extracted_entities", ["project_id"], unique=False)
    op.create_index("ix_research_extracted_entities_chunk_id", "research_extracted_entities", ["chunk_id"], unique=False)
    op.create_index(
        "ix_research_entities_project_id_entity_type",
        "research_extracted_entities",
        ["project_id", "entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_research_entities_project_id_created_at",
        "research_extracted_entities",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_research_entities_canonical_entity_id",
        "research_extracted_entities",
        ["canonical_entity_id"],
        unique=False,
    )

    op.create_table(
        "entity_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("from_entity_id", sa.Uuid(), nullable=False),
        sa.Column("to_entity_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("from_entity_id <> to_entity_id", name="ck_entity_relationships_no_self_loop"),
        sa.ForeignKeyConstraint(
            ["from_entity_id"],
            ["research_extracted_entities.id"],
            name="fk_er_from_ent",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_entity_id"],
            ["research_extracted_entities.id"],
            name="fk_er_to_ent",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entity_relationships"),
    )
    op.create_index("ix_entity_relationships_from_entity_id", "entity_relationships", ["from_entity_id"], unique=False)
    op.create_index("ix_entity_relationships_to_entity_id", "entity_relationships", ["to_entity_id"], unique=False)
    op.create_index(
        "ix_entity_relationships_relationship_type",
        "entity_relationships",
        ["relationship_type"],
        unique=False,
    )

    op.create_table(
        "aggregation_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_agg_snap_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_aggregation_snapshots"),
        sa.UniqueConstraint(
            "project_id",
            "snapshot_type",
            "period_key",
            name="uq_aggregation_snapshots_project_type_period",
        ),
    )
    op.create_index("ix_aggregation_snapshots_project_id", "aggregation_snapshots", ["project_id"], unique=False)
    op.create_index("ix_aggregation_snapshots_snapshot_type", "aggregation_snapshots", ["snapshot_type"], unique=False)
    op.create_index("ix_aggregation_snapshots_period_key", "aggregation_snapshots", ["period_key"], unique=False)
    op.create_index(
        "ix_aggregation_snapshots_project_id_created_at",
        "aggregation_snapshots",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "research_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column(
            "key_findings_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "facts_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "hypotheses_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "risks_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "opportunities_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "recommendations_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "open_questions_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_rsum_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_summaries"),
    )
    op.create_index("ix_research_summaries_project_id", "research_summaries", ["project_id"], unique=False)
    op.create_index(
        "ix_research_summaries_project_id_status",
        "research_summaries",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_research_summaries_project_id_updated_at",
        "research_summaries",
        ["project_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("research_summaries")
    op.drop_table("aggregation_snapshots")
    op.drop_table("entity_relationships")
    op.drop_table("research_extracted_entities")
    op.drop_table("text_chunks")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")
    op.drop_table("source_audios")
    op.drop_table("source_documents")
    op.drop_table("projects")
