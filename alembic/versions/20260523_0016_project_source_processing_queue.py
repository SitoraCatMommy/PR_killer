"""Project-wide source processing queue columns on source_documents and source_audios."""

from alembic import op
import sqlalchemy as sa


revision = "20260523_0016"
down_revision = "20260513_0015"
branch_labels = None
depends_on = None


def _add_queue_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="idle"),
    )
    op.add_column(
        table,
        sa.Column("processing_sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(table, sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("processing_last_error", sa.Text(), nullable=True))
    op.create_index(
        f"ix_{table}_project_processing",
        table,
        ["project_id", "processing_status"],
        unique=False,
    )


def upgrade() -> None:
    _add_queue_columns("source_documents")
    _add_queue_columns("source_audios")
    # Existing ingested sources are treated as already processed.
    op.execute("UPDATE source_documents SET processing_status = 'completed'")
    op.execute("UPDATE source_audios SET processing_status = 'completed'")


def downgrade() -> None:
    for table in ("source_audios", "source_documents"):
        op.drop_index(f"ix_{table}_project_processing", table_name=table)
        op.drop_column(table, "processing_last_error")
        op.drop_column(table, "processing_completed_at")
        op.drop_column(table, "processing_started_at")
        op.drop_column(table, "processing_sort_order")
        op.drop_column(table, "processing_status")
