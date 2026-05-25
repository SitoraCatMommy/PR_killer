"""Operational thresholds for transcript / chunk storage scaling (see docs/transcript_storage.md)."""

# Enable native RANGE/LIST partitioning on text_chunks (e.g. by month on created_at) when exceeded.
TEXT_CHUNKS_PARTITION_ROW_THRESHOLD = 5_000_000

# Rough heuristic: total table size on disk (bytes) — measure in prod with pg_total_relation_size.
TEXT_CHUNKS_PARTITION_SIZE_BYTES_THRESHOLD = 50 * 1024**3  # 50 GiB

# transcripts table: fewer rows but worth partitioning when very large or vacuum-heavy.
TRANSCRIPTS_PARTITION_ROW_THRESHOLD = 1_000_000
