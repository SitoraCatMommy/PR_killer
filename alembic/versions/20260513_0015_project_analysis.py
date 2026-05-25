"""Project-level LLM cache, public reports, and migration from batch tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260513_0015"
down_revision = "20260511_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_llm_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["project_id"],
            ["projects.id"],
            name="fk_project_llm_cache_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_llm_cache"),
        sa.UniqueConstraint("cache_key", name="uq_project_llm_cache_cache_key"),
    )
    op.create_index("ix_project_llm_cache_project_id", "project_llm_cache", ["project_id"], unique=False)
    op.create_index(
        "ix_project_llm_cache_project_kind",
        "project_llm_cache",
        ["project_id", "cache_kind"],
        unique=False,
    )

    op.create_table(
        "project_public_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=96), nullable=False),
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
            name="fk_project_public_reports_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_public_reports"),
        sa.UniqueConstraint("project_id", name="uq_project_public_reports_project_id"),
        sa.UniqueConstraint("token", name="uq_project_public_reports_token"),
    )

    op.create_table(
        "project_public_report_token_redirects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=96), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_public_report_token_redirects_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_public_report_token_redirects"),
        sa.UniqueConstraint("token", name="uq_project_public_report_token_redirects_token"),
    )
    op.create_index(
        "ix_project_public_report_token_redirects_project_id",
        "project_public_report_token_redirects",
        ["project_id"],
        unique=False,
    )

    # Migrate batch public tokens → project (newest batch per project wins primary token).
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO project_public_reports (id, project_id, token, created_at, updated_at)
            SELECT DISTINCT ON (rb.project_id)
                gen_random_uuid(),
                rb.project_id,
                bpr.token,
                bpr.created_at,
                bpr.updated_at
            FROM batch_public_reports bpr
            JOIN research_batches rb ON rb.id = bpr.batch_id
            ORDER BY rb.project_id, bpr.updated_at DESC NULLS LAST, bpr.created_at DESC
            ON CONFLICT (project_id) DO NOTHING
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO project_public_report_token_redirects (id, project_id, token)
            SELECT gen_random_uuid(), rb.project_id, bpr.token
            FROM batch_public_reports bpr
            JOIN research_batches rb ON rb.id = bpr.batch_id
            WHERE NOT EXISTS (
                SELECT 1 FROM project_public_reports ppr
                WHERE ppr.project_id = rb.project_id AND ppr.token = bpr.token
            )
            ON CONFLICT (token) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_public_report_token_redirects_project_id",
        table_name="project_public_report_token_redirects",
    )
    op.drop_table("project_public_report_token_redirects")
    op.drop_table("project_public_reports")
    op.drop_index("ix_project_llm_cache_project_kind", table_name="project_llm_cache")
    op.drop_index("ix_project_llm_cache_project_id", table_name="project_llm_cache")
    op.drop_table("project_llm_cache")
