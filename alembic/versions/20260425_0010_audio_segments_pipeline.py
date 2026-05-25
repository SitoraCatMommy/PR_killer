"""Chunked audio transcription: audio_segments + pipeline columns on source_audios."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260425_0010"
down_revision = "20260422_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_audios",
        sa.Column(
            "audio_pipeline_status",
            sa.String(length=32),
            server_default="ready",
            nullable=False,
        ),
    )
    op.add_column("source_audios", sa.Column("audio_pipeline_last_error", sa.Text(), nullable=True))
    op.add_column("source_audios", sa.Column("audio_file_bytes", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_source_audios_audio_pipeline_status",
        "source_audios",
        ["audio_pipeline_status"],
        unique=False,
    )

    op.create_table(
        "audio_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_audio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("segment_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=256), nullable=True),
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
            ["source_audio_id"],
            ["source_audios.id"],
            name="fk_audio_segments_source_audio_id_source_audios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audio_segments"),
        sa.UniqueConstraint("source_audio_id", "segment_index", name="uq_audio_segments_audio_index"),
    )
    op.create_index("ix_audio_segments_source_audio_id", "audio_segments", ["source_audio_id"], unique=False)
    op.create_index("ix_audio_segments_status", "audio_segments", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audio_segments_status", table_name="audio_segments")
    op.drop_index("ix_audio_segments_source_audio_id", table_name="audio_segments")
    op.drop_table("audio_segments")
    op.drop_index("ix_source_audios_audio_pipeline_status", table_name="source_audios")
    op.drop_column("source_audios", "audio_file_bytes")
    op.drop_column("source_audios", "audio_pipeline_last_error")
    op.drop_column("source_audios", "audio_pipeline_status")
