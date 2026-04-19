"""Add report_extras_json for smart report sections (talking points, word analysis, etc.)

Revision ID: 20260415_0004
Revises: 20260414_0003
Create Date: 2026-04-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260415_0004"
down_revision: Union[str, Sequence[str], None] = "20260414_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_reports",
        sa.Column(
            "report_extras_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_reports", "report_extras_json")
