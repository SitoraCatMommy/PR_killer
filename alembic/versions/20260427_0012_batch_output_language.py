"""Optional output_language on research_batches (overrides project for batch-scoped LLM)."""

import sqlalchemy as sa
from alembic import op

revision = "20260427_0012"
down_revision = "20260426_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_batches",
        sa.Column("output_language", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_batches", "output_language")
