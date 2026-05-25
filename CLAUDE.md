# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Docker (primary workflow)
```bash
make up-build          # Start all services with rebuild
make recreate-app      # Rebuild api + worker after code changes (faster than up-build)
make down              # Stop all services
make migrate           # Run alembic upgrade head inside api container
make test              # Run pytest inside api container
make logs-api          # Follow API logs
make logs-worker       # Follow Celery worker logs
make shell-api         # Interactive shell in api container
make web-dev           # Start Vite dev server (port 3000)
make demo-flow         # Run full end-to-end demo pipeline
```

### Local development (no Docker)
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# In a second terminal:
celery -A app.infrastructure.celery_app.celery_app worker --loglevel=info
```

### Quality
```bash
ruff check app          # Linting
mypy app                # Type checking (strict)
pytest                  # Tests
cd web && npm run lint  # Frontend linting
cd web && npm run build # TypeScript check + Vite build
cd web && npm run generate-api  # Regenerate types from OpenAPI schema
```

## Architecture

**Research Intelligence Agent** — ingests text documents and audio recordings into research projects, runs an async pipeline to transcribe, chunk, extract domain entities, and generate aggregated reports/dashboards.

### Request lifecycle
1. **HTTP** (FastAPI, port 8000) — accepts file uploads and config; returns `202 Accepted` with a Celery task ID for async work
2. **Celery** (Redis broker) — workers execute the processing pipeline
3. **PostgreSQL + pgvector** — persistent storage for all domain entities; pgvector enables embedding-based retrieval
4. **React frontend** (Vite, port 3000) — polls task status and renders projects, sources, transcripts, analytics

### Processing pipeline
```
Upload → project queue (pending → processing, PROJECT_QUEUE_CONCURRENCY sources at a time)
       → [audio] Transcribe (OpenAI/Gemini) → Chunk (fixed or semantic/OpenAI)
       → Extract entities (mock or GPT) → aggregate_project_sync per completed source
       → When queue idle: single LLM portrait/strategy/full-report over full project corpus
```

**Project queue** (replaces batch groups for product flows): status on `source_documents` / `source_audios`; drainer `process_project_processing_queue`; API `GET /projects/{id}/processing-queue`. Batch routes under `/batches` are deprecated — use project bulk upload + `POST /projects/{id}/process`.

### Key layers
| Layer | Path | Role |
|---|---|---|
| API routes | `app/api/v1/` | FastAPI routers; thin — validate, delegate to services |
| Services | `app/services/` | All business logic; each service is a single responsibility |
| Repositories | `app/repositories/` | SQLAlchemy async queries; no raw SQL in services |
| Models | `app/models/` | SQLAlchemy ORM (mapped dataclasses) |
| Schemas | `app/schemas/` | Pydantic v2 request/response contracts |
| Workers | `app/workers/tasks/` | Celery task definitions (thin wrappers around services) |
| Infrastructure | `app/infrastructure/` | Settings (pydantic-settings), Celery app, pluggable storage |

### Pluggable providers
Configured via environment variables (see `.env.example`):
- **Transcription**: `openai_provider.py` or `gemini_provider.py` — selected by `TRANSCRIPTION_PROVIDER`
- **Extraction**: `gpt_provider.py` or `mock_provider.py` — selected by `EXTRACTION_PROVIDER`
- **Chunking**: fixed-size or semantic (`openai_semantic_chunking_service.py`) — selected by `CHUNKING_STRATEGY`
- **Storage**: `local.py` — pluggable via `app/infrastructure/storage/`

### Frontend
- React 19 + TypeScript, React Router 7, TanStack Query 5 for server state
- `web/src/api/schema.d.ts` is **generated** — run `npm run generate-api` after backend schema changes
- `web/src/api/api.ts` wraps generated types; `client.ts` is the axios/fetch base client

### Database migrations
Alembic — all migrations in `alembic/versions/`. The domain was built in phases; newer tables live in `research_*` migrations. Legacy tables (`materials`, `insights`) support the demo pipeline only.

## Configuration
All settings are in `app/infrastructure/settings.py` (pydantic-settings). The key provider switches:
- `TRANSCRIPTION_PROVIDER` — `openai` | `gemini`
- `EXTRACTION_PROVIDER` — `gpt` | `mock`
- `CHUNKING_STRATEGY` — `fixed` | `semantic`
- `SUMMARY_PROVIDER` — controls report generation backend
- `PROJECT_QUEUE_ENABLED` — `true` (default): limited parallel queue; `false`: legacy fan-out all sources
- `PROJECT_QUEUE_CONCURRENCY` — default `1` (raise to `2`–`3` for faster throughput)

Copy `.env.example` → `.env` and populate API keys before running.
