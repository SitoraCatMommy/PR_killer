"""Add projects.output_language for report generation language (ru|uz|en)."""

from alembic import op
import sqlalchemy as sa


revision = "20260420_0005"
down_revision = "20260415_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "output_language",
            sa.String(length=8),
            nullable=False,
            server_default="ru",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "output_language")
