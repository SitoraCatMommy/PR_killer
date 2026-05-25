"""Public read-only report links (opaque token per batch)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260422_0008"
down_revision = "20260421_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batch_public_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["batch_id"],
            ["research_batches.id"],
            name="fk_batch_public_reports_batch_id_research_batches",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batch_public_reports"),
        sa.UniqueConstraint("batch_id", name="uq_batch_public_reports_batch_id"),
        sa.UniqueConstraint("token", name="uq_batch_public_reports_token"),
    )
    op.create_index("ix_batch_public_reports_batch_id", "batch_public_reports", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_batch_public_reports_batch_id", table_name="batch_public_reports")
    op.drop_table("batch_public_reports")
