# Research Intelligence Agent — Backend

Production-minded FastAPI backend for ingesting **text** and **audio** research materials, running a **Celery** pipeline (transcribe → normalize → extract entities → deduplicated insights with **pgvector** embeddings → dashboard aggregates), backed by **PostgreSQL**, **Redis**, and **SQLAlchemy 2.0** (async API + sync workers).

## Stack

- Python **3.12**, **FastAPI**, **Pydantic v2**, **Uvicorn**
- **PostgreSQL** + **pgvector**, **SQLAlchemy 2.0** (async `asyncpg`, sync `psycopg` in workers)
- **Alembic** migrations
- **Redis** + **Celery**
- **Docker** / **Docker Compose**

## Layout (clean architecture)

| Package | Role |
|--------|------|
| `app/api` | HTTP routers, versioning, dependencies |
| `app/domain` | Enums and domain dataclasses |
| `app/services` | Orchestration (normalization, transcription, extraction, dedup, aggregates) |
| `app/repositories` | Persistence accessors |
| `app/workers` | Celery tasks |
| `app/infrastructure` | Settings, DB engines, Redis, Celery app |
| `app/models` | SQLAlchemy ORM |
| `app/schemas` | Pydantic request/response models |

## Database schema (Step 2 — research domain)

Additive tables (revision `20250403_0002`) model projects, sources, transcripts, chunks, extracted entities, relationships, snapshots, and summaries. Legacy skeleton tables (`materials`, `insights`, `extracted_entities`, …) remain for the existing demo pipeline.

| Table | Purpose |
|-------|---------|
| `projects` | Top-level research workspace |
| `source_documents` | Ingested text / file metadata (`SourceType`) |
| `source_audios` | Audio assets linked to a project |
| `transcripts` | ASR output for an audio (`JobStatus`, provider) |
| `transcript_segments` | Time-bounded segments of a transcript |
| `text_chunks` | Chunked text for RAG / embeddings (`embedding` is `vector(1536)`) |
| `research_extracted_entities` | Structured entities (`EntityType`), always tied to a `text_chunks` row |
| `entity_relationships` | Graph edges (`RelationshipType`), no self-loops |
| `aggregation_snapshots` | Per-project dashboard payloads keyed by `snapshot_type` + `period_key` |
| `research_summaries` | Generated summaries (`SummaryStatus`) + structured JSON sections |

**Traceability:** `text_chunks` and `research_extracted_entities` enforce a DB `CHECK` that **exactly one** of `source_document_id`, `source_audio_id`, or `transcript_id` is set. Every domain entity row also has a **non-null** `chunk_id` back to `text_chunks`.

**Legacy naming:** Rows in the old `extracted_entities` table are mapped by ORM class `MaterialExtractedEntity` (material pipeline). Domain entities use ORM class `ExtractedEntity` and table `research_extracted_entities`.

**PostgreSQL:** constraint and index names are kept **≤ 63 characters** (e.g. short `fk_*` names in migration `20250403_0002`).

## Quick start (Docker)

1. Copy environment file:

   ```bash
   cp .env.example .env
   ```

2. Adjust Compose URLs in `.env` (defaults match `docker-compose.yml`):

   - `DATABASE_URL=postgresql+asyncpg://ria:ria@postgres:5432/research_intel`
   - `DATABASE_URL_SYNC=postgresql+psycopg://ria:ria@postgres:5432/research_intel`
   - `REDIS_URL=redis://redis:6379/0`
   - `CELERY_BROKER_URL=redis://redis:6379/1`
   - `CELERY_RESULT_BACKEND=redis://redis:6379/2`

3. Build and run:

   ```bash
   docker compose up --build
   ```

4. In another terminal, run migrations inside the API container:

   ```bash
   docker compose exec api alembic upgrade head
   ```

5. Open API docs: `http://localhost:8000/docs`

**Services:** `api` (FastAPI), `worker` (Celery), `postgres` (pgvector), `redis`. Shared volume `uploads` stores audio at `/data/uploads` for both API and worker.

## Local development (without Docker)

Requires Python **3.12**, PostgreSQL with **pgvector**, and Redis.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Celery worker (separate shell):

```bash
celery -A app.infrastructure.celery_app.celery_app worker --loglevel=info
```

## API overview

### Health

- `GET /api/v1/health` — liveness
- `GET /api/v1/health/ready` — Redis connectivity

### Research domain (Step 3 — ingestion & retrieval)

These routes use the Step 2 schema (`projects`, `source_documents`, `source_audios`, …). Heavy work is queued on **Celery** (transcribe, chunk, extract).

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/projects` | Create project |
| `GET` | `/api/v1/projects` | List projects (paginated) |
| `GET` | `/api/v1/projects/{project_id}` | Project by id |
| `POST` | `/api/v1/projects/{project_id}/sources/text/upload` | Multipart text file upload |
| `POST` | `/api/v1/projects/{project_id}/sources/audio/upload` | Multipart audio upload |
| `POST` | `/api/v1/projects/{project_id}/sources/text/raw` | JSON body: raw text note |
| `GET` | `/api/v1/projects/{project_id}/sources` | Unified list: `documents` + `audios` (paginated) |
| `GET` | `/api/v1/sources/documents/{source_document_id}` | Document detail + counts (`text_chunks_count`, `extracted_entities_count`) |
| `GET` | `/api/v1/sources/audios/{source_audio_id}` | Audio detail + transcript + counts |
| `POST` | `/api/v1/sources/audios/{source_audio_id}/transcribe` | Queue transcription → `transcripts` + segments (**202** + `task_id`) |
| `POST` | `/api/v1/sources/documents/{source_document_id}/chunk` | Queue fixed-size chunking → `text_chunks` (**202**) |
| `POST` | `/api/v1/sources/documents/{source_document_id}/chunk/semantic` | Queue OpenAI semantic chunking → `text_chunks` (**202**, requires `OPENAI_API_KEY`) |
| `POST` | `/api/v1/sources/documents/{source_document_id}/extract` | Queue research entity extraction (**202**) |
| `POST` | `/api/v1/transcripts/{transcript_id}/chunk` | Queue fixed-size chunking for transcript text (**202**) |
| `POST` | `/api/v1/transcripts/{transcript_id}/chunk/semantic` | Queue OpenAI semantic chunking for transcript (**202**, requires `OPENAI_API_KEY`) |
| `POST` | `/api/v1/transcripts/{transcript_id}/extract` | Queue extraction for transcript-linked chunks (**202**) |
| `GET` | `/api/v1/projects/{project_id}/entities` | Filtered entity list (`entity_type`, `min_confidence`, source/transcript ids, `limit`/`offset`) |
| `POST` | `/api/v1/projects/{project_id}/aggregate` | Queue dedup + `aggregation_snapshots` dashboard payload (**202**) |
| `GET` | `/api/v1/projects/{project_id}/aggregation` | Latest research aggregation snapshot JSON (or `snapshot: null`) |
| `POST` | `/api/v1/projects/{project_id}/summary/generate` | Queue deterministic summary from entities + snapshot (**202**) |
| `GET` | `/api/v1/projects/{project_id}/summary` | Latest `research_summaries` row, or **404** if none |

**Uploads:** files are stored under `UPLOAD_STORAGE_PATH` (default `/data/uploads`, Docker Compose sets this on `api` and `worker`). Plain-text uploads populate `raw_text` on `source_documents`; other text-like types store metadata and path only until a parser exists.

**Text chunking:** `CHUNK_MAX_CHARS` (default `500`) and `CHUNK_OVERLAP_CHARS` (default `80`) configure `ChunkingService` for **both** document chunking (`chunk_source_document_sync`) and transcript chunking (`chunk_transcript_sync`). Set them in `.env` (see `.env.example`). If `CHUNK_OVERLAP_CHARS` ≥ `CHUNK_MAX_CHARS`, overlap is clamped to `max − 1` when settings load.

**Semantic (OpenAI) chunking:** With `OPENAI_API_KEY` set (API and **worker** in Docker Compose), use `POST /api/v1/sources/documents/{id}/chunk/semantic` or `POST /api/v1/transcripts/{id}/chunk/semantic` to queue Celery jobs that split text into meaning-oriented segments via `OpenAISemanticChunkingService` (`OPENAI_SEMANTIC_CHUNK_MODEL`, default `gpt-4o-mini`; long inputs are batched using `OPENAI_SEMANTIC_CHUNK_WINDOW_CHARS`). Resulting `text_chunks.metadata_json` includes `chunking_strategy: openai` and `semantic_model`. Fixed-size chunking remains on `POST .../chunk` (documents) and `POST /transcripts/{id}/chunk`.

**Example — create project and upload text:**

```bash
BASE=http://localhost:8000/api/v1
PID=$(curl -s -X POST "$BASE/projects" -H "Content-Type: application/json" \
  -d '{"name":"Demo"}' | jq -r .id)

curl -s -X POST "$BASE/projects/$PID/sources/text/upload" \
  -F "file=@./notes.txt" -F "source_type=upload"

curl -s -X POST "$BASE/projects/$PID/sources/text/raw" \
  -H "Content-Type: application/json" \
  -d '{"title":"Scratch","text":"Hello from API"}'

curl -s "$BASE/projects/$PID/sources?limit=20&offset=0" | jq .
```

**Example — audio upload:**

```bash
curl -s -X POST "$BASE/projects/$PID/sources/audio/upload" \
  -F "file=@./recording.m4a" -F "source_type=upload"
```

OpenAPI: `http://localhost:8000/docs` (form fields for multipart endpoints are documented there).

#### Research extraction (Step 5)

- **Input:** existing `text_chunks` for a document or transcript (run **chunk** / **transcribe** + **chunk_transcript** first).
- **Behavior:** Celery task deletes prior `research_extracted_entities` for that document or transcript, then runs the configured provider per chunk and inserts new rows (traceable via `chunk_id` + source surface).
- **Provider:** `RESEARCH_EXTRACTION_PROVIDER` — **`gpt`** (default when configured) uses OpenAI (`OPENAI_EXTRACTION_MODEL`, default `gpt-4o-mini`) to return JSON entities (concise insights, not verbatim copy). If `OPENAI_API_KEY` is unset, the factory **falls back to `mock`**. **`mock`** splits masked text into sentences/clauses, then emits **several** short entities per chunk (insight → `claim` + tag, recommendation → `custom` + tag, `risk` / `hypothesis` / `opportunity`, numeric → `metric`, URL/email → `reference` / `custom`). Service-level validation still caps at **8** entities per chunk and rejects full-chunk copies / overlong content.
- **Real vs mock:** Mock is rule-based and stable for CI or offline use; GPT is selected via settings without changing the task surface.
- **Optional Celery task:** `extract_entities_for_audio` — processes all chunks tied to an audio (direct `source_audio_id` or via transcripts).

**Manual flow (document):**

```bash
BASE=http://localhost:8000/api/v1
# … create project, upload text with raw_text, note DOC_ID …
curl -s -X POST "$BASE/sources/documents/$DOC_ID/chunk" | jq .
# wait for worker
curl -s -X POST "$BASE/sources/documents/$DOC_ID/extract" | jq .
curl -s "$BASE/projects/$PID/entities?entity_type=topic&min_confidence=0.6" | jq .
```

**Manual flow (transcript):** transcribe audio (Celery also runs fixed-size `chunk_transcript` in the same job) → optional `POST /transcripts/{transcript_id}/chunk` or `.../chunk/semantic` to re-chunk → `POST /transcripts/{transcript_id}/extract`.

#### Aggregation & summary (Step 6)

- **Dedup:** `ResearchAggregationService` clears `canonical_entity_id`, groups rows by deterministic fingerprint (`entity_type` + normalized title/content), keeps earliest row as canonical, links duplicates via `canonical_entity_id`.
- **Snapshot:** Upserts `aggregation_snapshots` with `snapshot_type=research_entities`, `period_key=all_time`, payload: type distribution, flattened tag counts, confidence buckets, top clusters (`member_entity_ids`), monthly `time_buckets`, totals.
- **Summary:** `RESEARCH_SUMMARY_PROVIDER` — **`gpt`** (default when `OPENAI_API_KEY` is set) loads canonical entities and calls OpenAI (`OPENAI_SUMMARY_MODEL`) for a narrative `summary_text` plus section arrays (`title`, `content`, `supporting_entity_ids`). If the key is missing or the call fails, **`SummaryService`** (deterministic) runs instead: sections from **canonical** entities (each item includes `entity_id`, `chunk_id`, optional `evidence_quote`); `summary_text` is a short factual header. Set `RESEARCH_SUMMARY_PROVIDER=deterministic` to force the non-LLM path. Re-run creates an additional summary row; `GET /summary` returns the latest by `updated_at`.
- **Order:** run **extract** → **aggregate** → **summary/generate** → `GET /summary` and `GET /aggregation`.

```bash
curl -s -X POST "$BASE/projects/$PID/aggregate" | jq .
# wait for worker
curl -s "$BASE/projects/$PID/aggregation" | jq '.snapshot.payload_json.totals'
curl -s -X POST "$BASE/projects/$PID/summary/generate" | jq .
curl -s "$BASE/projects/$PID/summary" | jq '.key_findings_json, .facts_json'
```

### Legacy demo pipeline (materials / insights)

- `POST /api/v1/materials/text` — ingest text (queues Celery pipeline)
- `POST /api/v1/materials/audio` — multipart audio (saved under uploads volume, queues pipeline)
- `GET /api/v1/materials`, `GET /api/v1/materials/{id}`, `POST /api/v1/materials/{id}/reprocess`
- `GET /api/v1/insights`
- `GET /api/v1/dashboard/aggregates`, `POST /api/v1/dashboard/aggregates/recompute`

## Pipeline behavior

1. **Audio** materials: `TranscriptionService` (`RESEARCH_TRANSCRIPTION_PROVIDER`: `mock`, `openai`, `whisper_local`, or `http`) produces `raw_text`.
2. **Normalization**: NFC Unicode + whitespace cleanup.
3. **Entity extraction**: deterministic placeholder (URLs, emails, markdown headings); replace with NER/LLM as needed.
4. **Insights**: stub insight per material with **zero vector** embedding (dimension **1536**); **dedup** via `dedup_key` unique constraint.
5. **Aggregates**: Celery task recomputes dashboard rows (`material_counts`, `insight_counts`, `entity_frequency`, `pipeline_health`).

## Configuration

See `.env.example`. Important keys:

- `UPLOAD_STORAGE_PATH` — root for research + material file storage (default `/data/uploads`; Compose uses the `uploads` volume)
- `RESEARCH_EXTRACTION_PROVIDER` — `gpt` (default): OpenAI extraction; falls back to `mock` if `OPENAI_API_KEY` is empty. Use `mock` for deterministic, offline-friendly extraction.
- `RESEARCH_SUMMARY_PROVIDER` — `gpt` (default): OpenAI summary; falls back to deterministic `SummaryService` without a key. Use `deterministic` to skip the LLM.
- `OPENAI_EXTRACTION_MODEL` / `OPENAI_SUMMARY_MODEL` — chat models for extraction and summary (default `gpt-4o-mini`).
- `OPENAI_API_KEY` — required for GPT extraction/summary and semantic chunking.
- `RESEARCH_TRANSCRIPTION_PROVIDER` — `mock` (default), `openai` (needs `OPENAI_API_KEY` + `OPENAI_TRANSCRIPTION_MODEL`, e.g. `whisper-1`), `whisper_local` (OpenAI Whisper CLI on worker `PATH`), or `http` (+ `TRANSCRIPTION_API_URL`). Optional: `RESEARCH_TRANSCRIPTION_FALLBACK_TO_MOCK=true` to return mock text after a provider failure instead of failing the task.
- `EMBEDDING_DIMENSION` — informational for future embedding models; ORM vector column size is fixed in migrations (`1536`) and must stay aligned when you change models
- `CORS_ORIGINS` — `*` or comma-separated list

## Testing / quality

```bash
ruff check app
mypy app
pytest
```

(Tests are minimal in this skeleton; extend under `tests/`.)

## License

Proprietary / your choice — add a `LICENSE` file as needed.
