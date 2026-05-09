from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="research-intelligence-agent", alias="APP_NAME")
    app_env: Literal["local", "dev", "staging", "prod"] = Field(default="local", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    cors_origins: str = Field(
        default="*",
        alias="CORS_ORIGINS",
        description="Comma-separated origins; use explicit hosts in production.",
    )

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    upload_storage_path: str = Field(
        default="/data/uploads",
        alias="UPLOAD_STORAGE_PATH",
        description="Root directory for LocalFileStorage (bind-mounted in Docker).",
    )
    upload_max_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1,
        le=1024 * 1024 * 1024,
        alias="UPLOAD_MAX_BYTES",
        description="Maximum accepted request upload size for source/material files.",
    )
    upload_max_files: int = Field(
        default=50,
        ge=1,
        le=500,
        alias="UPLOAD_MAX_FILES",
        description="Maximum number of files accepted by a single bulk upload request.",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://ria:ria@localhost:5432/research_intel",
        alias="DATABASE_URL",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://ria:ria@localhost:5432/research_intel",
        alias="DATABASE_URL_SYNC",
    )

    redis_url: RedisDsn = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        alias="CELERY_BROKER_URL",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        alias="CELERY_RESULT_BACKEND",
    )

    embedding_dimension: int = Field(default=1536, ge=8, le=8192, alias="EMBEDDING_DIMENSION")

    research_transcription_provider: Literal["mock", "openai", "whisper_local", "http"] = Field(
        default="mock",
        alias="RESEARCH_TRANSCRIPTION_PROVIDER",
        description=(
            "Research ASR: `mock` placeholder; `openai` OpenAI Audio Transcriptions; "
            "`whisper_local` `whisper` CLI on disk; `http` custom `TRANSCRIPTION_API_URL`."
        ),
    )
    research_transcription_fallback_to_mock: bool = Field(
        default=False,
        alias="RESEARCH_TRANSCRIPTION_FALLBACK_TO_MOCK",
        description=(
            "If true, on provider failure return mock text instead of failing the Celery task."
        ),
    )
    transcription_api_url: str | None = Field(default=None, alias="TRANSCRIPTION_API_URL")
    transcription_api_key: str | None = Field(default=None, alias="TRANSCRIPTION_API_KEY")

    openai_transcription_model: str = Field(
        default="whisper-1",
        alias="OPENAI_TRANSCRIPTION_MODEL",
        description="OpenAI speech-to-text model (e.g. whisper-1, gpt-4o-mini-transcribe).",
    )
    openai_transcription_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        le=3600.0,
        alias="OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS",
    )

    whisper_local_command: str = Field(
        default="whisper",
        alias="WHISPER_LOCAL_COMMAND",
        description=(
            "Executable for RESEARCH_TRANSCRIPTION_PROVIDER=whisper_local "
            "(openai-whisper CLI)."
        ),
    )
    whisper_local_model: str = Field(
        default="base",
        alias="WHISPER_LOCAL_MODEL",
    )
    whisper_local_timeout_seconds: float = Field(
        default=3600.0,
        ge=60.0,
        le=86400.0,
        alias="WHISPER_LOCAL_TIMEOUT_SECONDS",
    )

    research_extraction_provider: Literal["mock", "gpt"] = Field(
        default="gpt",
        alias="RESEARCH_EXTRACTION_PROVIDER",
        description=(
            "Entity extraction: `mock` rules, `gpt` OpenAI "
            "(falls back to mock if no API key)."
        ),
    )
    research_summary_provider: Literal["deterministic", "gpt"] = Field(
        default="gpt",
        alias="RESEARCH_SUMMARY_PROVIDER",
        description=(
            "Summary: `deterministic` buckets entities; `gpt` synthesizes via OpenAI "
            "(falls back if no key)."
        ),
    )

    chunk_max_chars: int = Field(
        default=500,
        ge=64,
        le=32000,
        alias="CHUNK_MAX_CHARS",
        description="Max characters per `text_chunks.text` segment (documents & transcripts).",
    )
    chunk_overlap_chars: int = Field(
        default=80,
        ge=0,
        le=16000,
        alias="CHUNK_OVERLAP_CHARS",
        description="Character overlap between consecutive chunks (context carry).",
    )

    openai_api_key: str | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
        description="API key for OpenAI (chunking, extraction, summary).",
    )
    openai_extraction_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_EXTRACTION_MODEL",
        description="Chat model for research entity extraction.",
    )
    openai_summary_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_SUMMARY_MODEL",
        description="Chat model for research summary generation.",
    )
    openai_report_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_REPORT_MODEL",
        description="Chat model for structured ResearchReport (RU) generation.",
    )
    research_report_generation_debug: bool = Field(
        default=False,
        alias="RESEARCH_REPORT_GENERATION_DEBUG",
        description="Log counts and section sizes after ResearchReport LLM generation.",
    )
    research_report_brand_name: str = Field(
        default="Click",
        alias="RESEARCH_REPORT_BRAND_NAME",
        description="Brand name for PR report framing (never substitute in LLM prompts).",
    )
    pr_report_min_synthesis_entities: int = Field(
        default=3,
        ge=1,
        le=100,
        alias="PR_REPORT_MIN_SYNTHESIS_ENTITIES",
        description=(
            "Minimum PR-synthesis entities required before spending tokens on report generation."
        ),
    )
    pr_report_max_auto_extract_chunks: int = Field(
        default=40,
        ge=0,
        le=10000,
        alias="PR_REPORT_MAX_AUTO_EXTRACT_CHUNKS",
        description=(
            "Maximum chunks the report job may auto-extract before blocking for explicit prep."
        ),
    )
    pr_report_auto_prepare: bool = Field(
        default=True,
        alias="PR_REPORT_AUTO_PREPARE",
        description=(
            "If true, report jobs may perform bounded chunk/extract/aggregate prep "
            "before generation."
        ),
    )
    pr_report_max_prompt_chars: int = Field(
        default=45000,
        ge=8000,
        le=118000,
        alias="PR_REPORT_MAX_PROMPT_CHARS",
        description="Maximum JSON payload characters sent to the PR report model.",
    )
    pr_report_max_repair_attempts: int = Field(
        default=1,
        ge=0,
        le=3,
        alias="PR_REPORT_MAX_REPAIR_ATTEMPTS",
        description="Maximum compact repair calls after an invalid PR report model response.",
    )

    external_research_provider: Literal["mock", "http"] = Field(
        default="mock",
        alias="EXTERNAL_RESEARCH_PROVIDER",
        description=(
            "External literature: `mock` placeholders, `http` POST to "
            "EXTERNAL_RESEARCH_API_URL."
        ),
    )
    external_research_api_url: str | None = Field(default=None, alias="EXTERNAL_RESEARCH_API_URL")
    external_research_api_key: str | None = Field(default=None, alias="EXTERNAL_RESEARCH_API_KEY")
    external_research_timeout_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=300.0,
        alias="EXTERNAL_RESEARCH_TIMEOUT_SECONDS",
    )

    openai_semantic_chunk_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_SEMANTIC_CHUNK_MODEL",
        description="Chat model for semantic text splitting into `text_chunks`.",
    )
    openai_semantic_chunk_window_chars: int = Field(
        default=24000,
        ge=4000,
        le=100000,
        alias="OPENAI_SEMANTIC_CHUNK_WINDOW_CHARS",
        description="Max characters per OpenAI request when splitting long documents (batched).",
    )

    @model_validator(mode="after")
    def _chunk_overlap_lt_max(self) -> Self:
        if self.chunk_overlap_chars >= self.chunk_max_chars:
            object.__setattr__(self, "chunk_overlap_chars", max(0, self.chunk_max_chars - 1))
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_allow_credentials(self) -> bool:
        return self.cors_origins.strip() != "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
