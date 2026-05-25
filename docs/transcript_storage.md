# Transcript storage and retrieval

This document is the canonical reference for how audio becomes searchable text in this codebase, and how we scale storage in PostgreSQL.

## Ingestion contract (audio → LLM-ready text)

1. **`source_audios`** — Uploaded interview file metadata and paths (`original_path`, pipeline status).
2. **`audio_segments`** — Optional time slices for chunked ASR; **`transcript_text`** holds the raw text per slice while the pipeline runs. This is **staging** data, not the canonical transcript for downstream NLP.
3. **`transcripts`** — **Canonical merged transcript** per audio (`full_text`, `language`, `status`, `provider_name`). After a successful chunked merge, older transcript rows for that `source_audio_id` are replaced (see `audio_segment_pipeline`).
4. **`transcript_segments`** — Optional structured lines (speaker, time range, text). May hold previews or ASR-aligned segments; **retrieval for chunking/embeddings uses `transcripts` + `text_chunks`**.
5. **`text_chunks`** — **Retrieval unit** for extraction, embeddings, and RAG-style prompts. Each row references exactly one of `source_document_id`, `source_audio_id`, or `transcript_id` (see check constraint). For audio-first flow, chunks are typically tied to **`transcript_id`** after merge.

Downstream OpenAI / extraction jobs should prefer **`text_chunks`** (ordered by `chunk_index`) for long corpora; use **`transcripts.full_text`** when a single contiguous string is required (e.g. smaller files or debugging).

## Batches (multi-research per project)

A **research batch** (`research_batches`) selects sources via **`research_batch_sources`** (each row links either a `source_document_id` or `source_audio_id`).

To assemble all text for a selected study in **stable order** (batch source insertion order, then chunk order within each source), use **`app.services.batch_corpus_service`**:

- `list_text_chunks_for_batch_ordered_sync` / `list_text_chunks_for_batch_ordered`
- `merged_corpus_text_for_batch_sync` / `merged_corpus_text_for_batch`

For SQL filters (e.g. dashboards, analytics), use **`text_chunks_scope_and`** so `project_id` and source ID sets stay consistent.

## Indexes (FTS + vectors)

- **Full-text search:** GIN indexes on `to_tsvector('simple', …)` for `transcripts.full_text` and `text_chunks.text`. The **`simple`** dictionary avoids English-specific stemming and behaves reasonably for mixed-language research text.
- **Semantic search:** Partial **HNSW** index on `text_chunks.embedding` (`vector_cosine_ops`) for approximate nearest-neighbor queries when embeddings are populated.

## Partitioning thresholds (operational guidance)

Enable **native PostgreSQL partitioning** (e.g. by month on `created_at`) when **either**:

| Table         | Suggested threshold                         | Rationale                                      |
|---------------|---------------------------------------------|------------------------------------------------|
| `text_chunks` | **≥ 5M rows** or **≥ ~50 GB** table size   | Primary growth from chunking + re-ingestion   |
| `transcripts` | **≥ 1M rows** or maintenance pain on vacuum | Smaller rows but frequent updates on re-ASR   |

Until then, ** btree indexes + FTS GIN + selective HNSW** are sufficient. Partitioning is a migration-heavy step: schedule a maintenance window and revisit query patterns (especially `project_id` + time range filters).

Constants are also defined in code: `app.domain.transcript_storage_constants`.

## When to add OpenSearch / Elasticsearch

Only if PostgreSQL FTS + ranking latency or relevance is insufficient at sustained scale. Until then, **Postgres + pgvector** remains the single source of truth.
