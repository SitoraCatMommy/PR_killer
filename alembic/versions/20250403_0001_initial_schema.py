"""initial_schema

Revision ID: 20250403_0001
Revises:
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20250403_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("source_uri", sa.String(length=2048), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("audio_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("parent_material_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_materials"),
    )
    op.create_index("ix_materials_material_type", "materials", ["material_type"], unique=False)
    op.create_index("ix_materials_source_uri", "materials", ["source_uri"], unique=False)
    op.create_index("ix_materials_status", "materials", ["status"], unique=False)
    op.create_index("ix_materials_parent_material_id", "materials", ["parent_material_id"], unique=False)

    op.create_table(
        "insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("dedup_key", sa.String(length=128), nullable=False),
        sa.Column("canonical_insight_id", sa.Uuid(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_insight_id"],
            ["insights.id"],
            name="fk_insights_canonical_insight_id_insights",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_insights"),
        sa.UniqueConstraint("dedup_key", name="uq_insights_dedup_key"),
    )
    op.create_index("ix_insights_dedup_key", "insights", ["dedup_key"], unique=False)
    op.create_index("ix_insights_canonical_insight_id", "insights", ["canonical_insight_id"], unique=False)

    op.create_table(
        "dashboard_aggregates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dashboard_aggregates"),
        sa.UniqueConstraint("kind", "period_key", name="uq_dashboard_kind_period"),
    )
    op.create_index("ix_dashboard_aggregates_kind", "dashboard_aggregates", ["kind"], unique=False)
    op.create_index("ix_dashboard_aggregates_period_key", "dashboard_aggregates", ["period_key"], unique=False)

    op.create_table(
        "extracted_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("normalized_value", sa.String(length=1024), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name="fk_extracted_entities_material_id_materials",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extracted_entities"),
        sa.UniqueConstraint("material_id", "fingerprint", name="uq_entity_material_fingerprint"),
    )
    op.create_index("ix_extracted_entities_material_id", "extracted_entities", ["material_id"], unique=False)
    op.create_index("ix_extracted_entities_kind", "extracted_entities", ["kind"], unique=False)
    op.create_index("ix_extracted_entities_normalized_value", "extracted_entities", ["normalized_value"], unique=False)
    op.create_index("ix_extracted_entities_fingerprint", "extracted_entities", ["fingerprint"], unique=False)

    op.create_table(
        "insight_source_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("insight_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("quote", sa.String(length=4096), nullable=True),
        sa.Column(
            "locator",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["insight_id"],
            ["insights.id"],
            name="fk_insight_source_links_insight_id_insights",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name="fk_insight_source_links_material_id_materials",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_insight_source_links"),
    )
    op.create_index("ix_insight_source_links_insight_id", "insight_source_links", ["insight_id"], unique=False)
    op.create_index("ix_insight_source_links_material_id", "insight_source_links", ["material_id"], unique=False)


def downgrade() -> None:
    op.drop_table("insight_source_links")
    op.drop_table("extracted_entities")
    op.drop_table("dashboard_aggregates")
    op.drop_table("insights")
    op.drop_table("materials")
    op.execute("DROP EXTENSION IF EXISTS vector")
