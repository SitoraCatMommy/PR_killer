"""GIN full-text indexes on transcripts/text_chunks; HNSW index on text_chunks.embedding."""

from alembic import op

revision = "20260426_0011"
down_revision = "20260425_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Multilingual-friendly: no language-specific stemming.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_transcripts_full_text_fts
        ON transcripts USING gin (to_tsvector('simple', coalesce(full_text, '')));
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_text_chunks_text_fts
        ON text_chunks USING gin (to_tsvector('simple', coalesce(text, '')));
        """
    )
    # Approximate NN for cosine distance (typical for OpenAI embeddings).
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_text_chunks_embedding_hnsw
        ON text_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_text_chunks_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS ix_text_chunks_text_fts;")
    op.execute("DROP INDEX IF EXISTS ix_transcripts_full_text_fts;")
