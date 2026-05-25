import json
import logging
from typing import Annotated, Any, Literal
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import IngestionServiceDep, SettingsDep
from app.domain.enums import BatchSourceProcessingStatus, SourceType
from app.domain.research_languages import normalize_output_language
from app.infrastructure.database import DbSession
from app.models.project import Project
from app.models.research_batch import ResearchBatch
from app.models.research_batch_source import ResearchBatchSource
from app.models.source_audio import SourceAudio
from app.models.source_document import SourceDocument
from app.repositories.batch_public_report_repository import BatchPublicReportRepository
from app.repositories.interview_unit_repository import list_units_for_documents
from app.repositories.research_batch_repository import ResearchBatchRepository
from app.repositories.research_report_repository import ResearchReportRepository
from app.schemas.audio_pipeline import BatchAudioPipelineResponse
from app.schemas.common import ErrorResponse
from app.schemas.processing import ProcessingTaskQueued
from app.schemas.scenario_report import BatchScenarioReportResponse
from app.schemas.research_batch import (
    AudiencePortraitResponse,
    BatchCorpusRead,
    BatchDashboardResponse,
    BatchInterviewUnitsResponse,
    BatchPublicLinkResponse,
    FullReportResponse,
    InterviewUnitRead,
    MessageLabAnalyzeRequest,
    MessageLabAnalyzeResponse,
    PRStrategyResponse,
    SegmentCompareResponse,
    BatchReportGenerateRequest,
    BatchSourceAddRequest,
    BatchDocumentPipelineRecoverResponse,
    BulkUploadResponse,
    BulkUploadResultItem,
    ResearchBatchDetailRead,
    ResearchBatchRead,
    ResearchBatchSourceItemRead,
    ResearchBatchSourceRead,
    ResearchBatchUpdate,
)
from app.services.batch_queue_service import merge_batch_analysis_metadata
from app.services.batch_cached_llm_service import (
    build_full_report_response,
    get_or_create_audience_portrait_response,
    get_or_create_pr_strategy_response,
    invalidate_batch_llm_cache,
)
from app.services.docx_text_extraction import DOCX_ERROR_CODES, DOCX_ERROR_MESSAGES_EN
from app.services.batch_narrative_export_service import build_narrative_docx_bytes, build_narrative_pdf_bytes
from app.services.dashboard_export_service import (
    batch_dashboard_to_csv,
    build_dashboard_pack_zip,
    topics_bar_chart_svg,
)
from app.services.dashboard_chart_png import bar_chart_png
from app.services.message_lab_service import analyze_message_lab
from app.services.batch_document_pipeline_recovery_service import list_batch_documents_needing_recovery
from app.services.research_batch_dashboard_service import (
    DASHBOARD_GROUP_BY_FIELDS,
    build_batch_dashboard,
    is_audio_upload,
)
from app.services.audio_pipeline_progress_service import build_batch_audio_pipeline
from app.services.batch_corpus_service import build_batch_corpus_preview
from app.services.batch_scenario_report_service import build_batch_scenario_report
from app.services.segment_compare_service import compare_batch_segments
from app.services.research_report_export_service import (
    assert_report_exportable,
    build_research_report_excel_bytes,
    build_research_report_pptx_bytes,
    export_filename_stem,
)
from app.workers.tasks.batch_processing_queue import process_batch_processing_queue
from app.workers.tasks.research_batch_report import generate_batch_research_report

router = APIRouter(prefix="/batches", tags=["research-batches"])

_MAX_BULK_FILES = 100
_MAX_BATCH_SOURCES = 200


def _raise_invalid_group_by() -> None:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "invalid_group_by",
            "message": f"group_by must be one of: {', '.join(sorted(DASHBOARD_GROUP_BY_FIELDS))}",
        },
    )


def _dashboard_build_kwargs(
    *,
    group_by: str | None,
    segment_key: str | None,
    date_from: str | None,
    date_to: str | None,
    stopwords: bool,
    compare_segment_a: str | None,
    compare_segment_b: str | None,
) -> dict[str, Any]:
    if group_by is not None and group_by not in DASHBOARD_GROUP_BY_FIELDS:
        _raise_invalid_group_by()
    return {
        "group_by": group_by,
        "segment_key": segment_key,
        "date_from": date_from,
        "date_to": date_to,
        "stopwords": stopwords,
        "compare_segment_a": compare_segment_a,
        "compare_segment_b": compare_segment_b,
    }


def _effective_output_language(batch: ResearchBatch, proj: Project | None) -> str:
    b_lang = getattr(batch, "output_language", None)
    if b_lang and str(b_lang).strip():
        return normalize_output_language(str(b_lang), default="ru")
    return normalize_output_language(proj.output_language if proj else None, default="ru")


async def _batch_or_404(session: DbSession, batch_id: UUID):
    repo = ResearchBatchRepository(session)
    b = await repo.get(batch_id)
    if b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch not found"},
        )
    return b


async def _sources_as_items(session: DbSession, batch) -> list[ResearchBatchSourceItemRead]:
    items: list[ResearchBatchSourceItemRead] = []
    for s in batch.sources:
        if s.source_document_id:
            doc = await session.get(SourceDocument, s.source_document_id)
            fn = (doc.filename if doc else "") or ""
            meta = dict(doc.metadata_json or {}) if doc else {}
            kind: str = "document"
        else:
            aud = await session.get(SourceAudio, s.source_audio_id)
            fn = (aud.filename if aud else "") or ""
            meta = dict(aud.metadata_json or {}) if aud else {}
            kind = "audio"
        items.append(
            ResearchBatchSourceItemRead(
                id=s.id,
                batch_id=s.batch_id,
                source_document_id=s.source_document_id,
                source_audio_id=s.source_audio_id,
                created_at=s.created_at,
                processing_status=getattr(
                    s,
                    "processing_status",
                    BatchSourceProcessingStatus.COMPLETED.value,
                ),
                sort_order=int(getattr(s, "sort_order", 0) or 0),
                last_error=getattr(s, "last_error", None),
                started_at=getattr(s, "started_at", None),
                completed_at=getattr(s, "completed_at", None),
                source_kind=kind,  # type: ignore[arg-type]
                filename=fn,
                metadata_json=meta,
            )
        )
    return items


@router.get(
    "/{batch_id}",
    response_model=ResearchBatchDetailRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_batch(batch_id: UUID, session: DbSession) -> ResearchBatchDetailRead:
    b = await _batch_or_404(session, batch_id)
    sources = await _sources_as_items(session, b)
    return ResearchBatchDetailRead(
        id=b.id,
        project_id=b.project_id,
        name=b.name,
        description=b.description,
        output_language=getattr(b, "output_language", None),
        single_file_multi_interview_mode=getattr(b, "single_file_multi_interview_mode", True),
        created_at=b.created_at,
        updated_at=b.updated_at,
        sources=sources,
    )


@router.get(
    "/{batch_id}/interview-units",
    response_model=BatchInterviewUnitsResponse,
    responses={404: {"model": ErrorResponse}},
)
async def list_batch_interview_units(batch_id: UUID, session: DbSession) -> BatchInterviewUnitsResponse:
    b = await _batch_or_404(session, batch_id)
    doc_ids = [s.source_document_id for s in b.sources if s.source_document_id]
    rows = await list_units_for_documents(session, doc_ids, limit=2000)
    items = [
        InterviewUnitRead(
            id=u.id,
            source_document_id=u.source_document_id,
            unit_index=u.unit_index,
            speaker=u.speaker,
            language=u.language,
            language_confidence=u.language_confidence,
            split_method=u.split_method or "",
            text_preview=(u.raw_text or "")[:240],
        )
        for u in rows
    ]
    return BatchInterviewUnitsResponse(items=items)


@router.get(
    "/{batch_id}/corpus",
    response_model=BatchCorpusRead,
    responses={404: {"model": ErrorResponse}},
)
async def get_batch_corpus(
    batch_id: UUID,
    session: DbSession,
    max_chars: int = Query(
        default=120_000,
        ge=4_000,
        le=2_000_000,
        description="Maximum characters returned in `text` (full corpus may be larger).",
    ),
) -> BatchCorpusRead:
    """Return merged chunk text for all sources in the batch (order: batch source `created_at`, then chunk index)."""
    b = await _batch_or_404(session, batch_id)
    payload = await build_batch_corpus_preview(session, b, max_chars=max_chars)
    return BatchCorpusRead.model_validate(payload)


@router.get(
    "/{batch_id}/audio-pipeline",
    response_model=BatchAudioPipelineResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_batch_audio_pipeline(batch_id: UUID, session: DbSession) -> BatchAudioPipelineResponse:
    await _batch_or_404(session, batch_id)
    row = await build_batch_audio_pipeline(session, batch_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch not found"},
        )
    return row


@router.patch(
    "/{batch_id}",
    response_model=ResearchBatchRead,
    responses={404: {"model": ErrorResponse}},
)
async def update_batch(batch_id: UUID, body: ResearchBatchUpdate, session: DbSession) -> ResearchBatchRead:
    patch = body.model_dump(exclude_unset=True)
    repo = ResearchBatchRepository(session)
    b = await repo.update(batch_id, patch)
    if b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch not found"},
        )
    await session.commit()
    await session.refresh(b)
    if "single_file_multi_interview_mode" in patch or "output_language" in patch:
        await invalidate_batch_llm_cache(session, batch_id)
    return ResearchBatchRead.model_validate(b)


@router.get(
    "/{batch_id}/dashboard",
    response_model=BatchDashboardResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def get_batch_dashboard(
    batch_id: UUID,
    session: DbSession,
    group_by: str | None = Query(
        default=None,
        description="Optional segment field from source metadata_json (gender, age_range, segments, …).",
    ),
    segment_key: str | None = Query(
        default=None,
        description="Bucket label within group_by (same contract as dashboard-export).",
    ),
    date_from: str | None = Query(default=None, description="Inclusive metadata date lower bound (YYYY-MM-DD)."),
    date_to: str | None = Query(default=None, description="Inclusive metadata date upper bound (YYYY-MM-DD)."),
    stopwords: bool = Query(default=False, description="Apply stopword filter to n-gram tables."),
    compare_segment_a: str | None = Query(
        default=None,
        description="First segment label for optional PR taxonomy compare (requires group_by + compare_segment_b).",
    ),
    compare_segment_b: str | None = Query(default=None, description="Second segment label for compare."),
) -> BatchDashboardResponse:
    kwargs = _dashboard_build_kwargs(
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )
    b = await _batch_or_404(session, batch_id)
    payload = await build_batch_dashboard(session, b, **kwargs)
    return BatchDashboardResponse.model_validate(payload)


@router.get(
    "/{batch_id}/dashboard-export.csv",
    responses={404: {"model": ErrorResponse}},
)
async def export_batch_dashboard_csv(
    batch_id: UUID,
    session: DbSession,
    group_by: str | None = Query(default=None),
    segment_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    stopwords: bool = Query(default=False),
    compare_segment_a: str | None = Query(default=None),
    compare_segment_b: str | None = Query(default=None),
) -> Response:
    b = await _batch_or_404(session, batch_id)
    kwargs = _dashboard_build_kwargs(
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )
    payload = await build_batch_dashboard(session, b, **kwargs)
    csv_text = batch_dashboard_to_csv(payload)
    stem = export_filename_stem(b.name or "batch", batch_id)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}_dashboard.csv"'},
    )


@router.get(
    "/{batch_id}/charts/{chart_kind}.svg",
    responses={404: {"model": ErrorResponse}},
)
async def export_batch_chart_svg(
    batch_id: UUID,
    chart_kind: Literal["topics", "problems", "risks", "pr_taxonomy"],
    session: DbSession,
    group_by: str | None = Query(default=None),
    segment_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    stopwords: bool = Query(default=False),
    compare_segment_a: str | None = Query(default=None),
    compare_segment_b: str | None = Query(default=None),
) -> Response:
    b = await _batch_or_404(session, batch_id)
    kwargs = _dashboard_build_kwargs(
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )
    payload = await build_batch_dashboard(session, b, **kwargs)
    svg = topics_bar_chart_svg(payload, kind=chart_kind)
    return Response(
        content=svg.encode("utf-8"),
        media_type="image/svg+xml; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="chart_{chart_kind}.svg"'},
    )


@router.get(
    "/{batch_id}/charts/{chart_kind}.png",
    responses={404: {"model": ErrorResponse}},
)
async def export_batch_chart_png(
    batch_id: UUID,
    chart_kind: Literal["topics", "problems", "risks", "pr_taxonomy"],
    session: DbSession,
    group_by: str | None = Query(default=None),
    segment_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    stopwords: bool = Query(default=False),
    compare_segment_a: str | None = Query(default=None),
    compare_segment_b: str | None = Query(default=None),
) -> Response:
    b = await _batch_or_404(session, batch_id)
    kwargs = _dashboard_build_kwargs(
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )
    payload = await build_batch_dashboard(session, b, **kwargs)
    if chart_kind == "pr_taxonomy":
        rows = [r for r in (payload.get("pr_taxonomy_totals") or []) if isinstance(r, dict)]
        png = bar_chart_png(rows, title="pr_taxonomy", label_key="pr_signal_type", value_key="value")
    else:
        key = "topics_pie" if chart_kind == "topics" else "problems_bar" if chart_kind == "problems" else "risks_bar"
        rows = [r for r in (payload.get(key) or []) if isinstance(r, dict)]
        png = bar_chart_png(rows, title=key, label_key="label", value_key="value")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="chart_{chart_kind}.png"'},
    )


@router.get(
    "/{batch_id}/dashboard-pack.zip",
    responses={404: {"model": ErrorResponse}},
)
async def export_batch_dashboard_pack(
    batch_id: UUID,
    session: DbSession,
    group_by: str | None = Query(default=None),
    segment_key: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    stopwords: bool = Query(default=False),
    compare_segment_a: str | None = Query(default=None),
    compare_segment_b: str | None = Query(default=None),
) -> Response:
    b = await _batch_or_404(session, batch_id)
    kwargs = _dashboard_build_kwargs(
        group_by=group_by,
        segment_key=segment_key,
        date_from=date_from,
        date_to=date_to,
        stopwords=stopwords,
        compare_segment_a=compare_segment_a,
        compare_segment_b=compare_segment_b,
    )
    payload = await build_batch_dashboard(session, b, **kwargs)
    raw = build_dashboard_pack_zip(payload)
    stem = export_filename_stem(b.name or "batch", batch_id)
    return Response(
        content=raw,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{stem}_dashboard_pack.zip"'},
    )


@router.post(
    "/{batch_id}/message-lab/analyze",
    response_model=MessageLabAnalyzeResponse,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def post_message_lab_analyze(
    batch_id: UUID,
    session: DbSession,
    body: MessageLabAnalyzeRequest,
) -> MessageLabAnalyzeResponse:
    b = await _batch_or_404(session, batch_id)
    try:
        return await analyze_message_lab(session, b, body)
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "openai_not_configured", "message": "OPENAI_API_KEY is required"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "message_lab_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "message_lab_failed", "message": str(e)},
        ) from e


@router.get(
    "/{batch_id}/audience-portrait",
    response_model=AudiencePortraitResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_audience_portrait(
    batch_id: UUID,
    session: DbSession,
    recalculate: bool = Query(
        default=False,
        description="If true, bypass cache and regenerate.",
    ),
    group_by: str | None = Query(
        default=None,
        description="Metadata field for segment filter (requires segment_value).",
    ),
    segment_value: str | None = Query(
        default=None,
        description="Segment bucket label as in dashboard (e.g. female, 18–24).",
    ),
) -> AudiencePortraitResponse:
    if segment_value is not None and not segment_value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_segment", "message": "segment_value cannot be empty"},
        )
    if segment_value is not None and group_by is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "segment_requires_group_by",
                "message": "segment_value requires group_by",
            },
        )
    if group_by is not None and group_by not in DASHBOARD_GROUP_BY_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_group_by",
                "message": f"group_by must be one of: {', '.join(sorted(DASHBOARD_GROUP_BY_FIELDS))}",
            },
        )
    if segment_value is not None and len(segment_value) > 240:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "segment_too_long", "message": "segment_value is too long"},
        )

    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    lang = _effective_output_language(b, proj)

    try:
        return await get_or_create_audience_portrait_response(
            session,
            b,
            group_by=group_by,
            segment_value=segment_value.strip() if segment_value else None,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for audience portrait",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "portrait_generation_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "portrait_generation_failed", "message": str(e)},
        ) from e


@router.get(
    "/{batch_id}/pr-strategy",
    response_model=PRStrategyResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_pr_strategy(
    batch_id: UUID,
    session: DbSession,
    recalculate: bool = Query(
        default=False,
        description="If true, bypass cache and regenerate.",
    ),
    group_by: str | None = Query(
        default=None,
        description="Metadata field for segment filter (requires segment_value).",
    ),
    segment_value: str | None = Query(
        default=None,
        description="Segment bucket label as in dashboard.",
    ),
) -> PRStrategyResponse:
    if segment_value is not None and not segment_value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_segment", "message": "segment_value cannot be empty"},
        )
    if segment_value is not None and group_by is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "segment_requires_group_by",
                "message": "segment_value requires group_by",
            },
        )
    if group_by is not None and group_by not in DASHBOARD_GROUP_BY_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_group_by",
                "message": f"group_by must be one of: {', '.join(sorted(DASHBOARD_GROUP_BY_FIELDS))}",
            },
        )
    if segment_value is not None and len(segment_value) > 240:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "segment_too_long", "message": "segment_value is too long"},
        )

    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    lang = _effective_output_language(b, proj)

    try:
        return await get_or_create_pr_strategy_response(
            session,
            b,
            group_by=group_by,
            segment_value=segment_value.strip() if segment_value else None,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for PR strategy",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "pr_strategy_generation_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "pr_strategy_generation_failed", "message": str(e)},
        ) from e


@router.get(
    "/{batch_id}/full-report",
    response_model=FullReportResponse,
    responses={
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_full_report(
    batch_id: UUID,
    session: DbSession,
    recalculate: bool = Query(
        default=False,
        description="If true, bypass portrait/strategy cache for this batch.",
    ),
) -> FullReportResponse:
    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    lang = _effective_output_language(b, proj)

    try:
        return await build_full_report_response(
            session,
            b,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for full report",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "full_report_generation_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "full_report_generation_failed", "message": str(e)},
        ) from e


@router.post(
    "/{batch_id}/public-link",
    response_model=BatchPublicLinkResponse,
    responses={404: {"model": ErrorResponse}},
)
async def create_batch_public_link(
    batch_id: UUID, session: DbSession, settings: SettingsDep
) -> BatchPublicLinkResponse:
    await _batch_or_404(session, batch_id)
    repo = BatchPublicReportRepository(session)
    row = await repo.upsert_for_batch(batch_id)
    await session.commit()
    prefix = settings.api_v1_prefix.rstrip("/")
    return BatchPublicLinkResponse(
        token=row.token,
        report_path=f"{prefix}/report/public/{row.token}",
    )


@router.get(
    "/{batch_id}/export",
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def export_batch_narrative(
    batch_id: UUID,
    session: DbSession,
    settings: SettingsDep,
    export_format: Literal["pdf", "docx"] = Query(
        ...,
        alias="format",
        description="Narrative export: structured text as PDF or Word document.",
    ),
) -> Response:
    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    lang = _effective_output_language(b, proj)
    try:
        full = await build_full_report_response(
            session,
            b,
            output_language=lang,
            recalculate=False,
            settings=settings,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for narrative export",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "narrative_export_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "narrative_export_failed", "message": str(e)},
        ) from e

    if export_format == "pdf":
        payload = build_narrative_pdf_bytes(full, batch_name=b.name, lang=lang)
        media = "application/pdf"
        ext = "pdf"
    else:
        payload = build_narrative_docx_bytes(full, batch_name=b.name, lang=lang)
        media = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        ext = "docx"
    stem = export_filename_stem(str(batch_id))
    return Response(
        content=payload,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{stem}_narrative.{ext}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get(
    "/{batch_id}/report",
    response_model=BatchScenarioReportResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def get_batch_scenario_report(
    batch_id: UUID,
    session: DbSession,
    mode: Literal["pr_audit", "audience", "messaging"] = Query(
        ...,
        description="Packaged scenario: pr_audit | audience | messaging",
    ),
    recalculate: bool = Query(
        default=False,
        description="Deprecated: ignored. Scenario is always derived from cached dashboard/portrait/strategy (no new synthesis).",
    ),
) -> BatchScenarioReportResponse:
    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    lang = _effective_output_language(b, proj)

    try:
        return await build_batch_scenario_report(
            session,
            b,
            mode=mode,
            output_language=lang,
            recalculate=recalculate,
        )
    except ValueError as e:
        if str(e) == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for this report mode",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "scenario_report_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "scenario_report_failed", "message": str(e)},
        ) from e


@router.get(
    "/{batch_id}/compare",
    response_model=SegmentCompareResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def compare_batch_segments_endpoint(
    batch_id: UUID,
    session: DbSession,
    group_by: str = Query(..., description="Metadata field (gender, age_range, segments, …)."),
    segment_a: str = Query(..., description="First segment label as in dashboard segment_key."),
    segment_b: str = Query(..., description="Second segment label."),
) -> SegmentCompareResponse:
    gb = group_by.strip()
    if gb not in DASHBOARD_GROUP_BY_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_group_by",
                "message": f"group_by must be one of: {', '.join(sorted(DASHBOARD_GROUP_BY_FIELDS))}",
            },
        )
    sa = segment_a.strip()
    sb = segment_b.strip()
    if not sa or not sb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_segment", "message": "segment_a and segment_b are required"},
        )
    if len(sa) > 240 or len(sb) > 240:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "segment_too_long", "message": "segment value is too long"},
        )

    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    lang = _effective_output_language(b, proj)

    try:
        payload = await compare_batch_segments(
            session,
            b,
            group_by=gb,
            segment_a=sa,
            segment_b=sb,
            output_language=lang,
        )
        return SegmentCompareResponse.model_validate(payload)
    except ValueError as e:
        code = str(e)
        if code == "openai_api_key_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "openai_not_configured",
                    "message": "OPENAI_API_KEY is required for segment comparison",
                },
            ) from e
        if code == "invalid_group_by":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_group_by", "message": "Invalid group_by"},
            ) from e
        if code == "segment_a_unknown":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "segment_a_unknown",
                    "message": "segment_a does not match any interview metadata for this group_by",
                },
            ) from e
        if code == "segment_b_unknown":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "segment_b_unknown",
                    "message": "segment_b does not match any interview metadata for this group_by",
                },
            ) from e
        if code == "segments_equal":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "segments_equal", "message": "segment_a and segment_b must differ"},
            ) from e
        if code == "segment_no_interviews":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "segment_no_interviews",
                    "message": "Each segment must include at least one interview in this batch",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "segment_compare_failed", "message": code},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "segment_compare_failed", "message": str(e)},
        ) from e


@router.post(
    "/{batch_id}/sources",
    response_model=ResearchBatchSourceRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def add_batch_source(
    batch_id: UUID,
    body: BatchSourceAddRequest,
    session: DbSession,
) -> ResearchBatchSourceRead:
    try:
        body.surface()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_source_payload",
                "message": "Send exactly one of source_document_id or source_audio_id",
            },
        ) from e
    b = await _batch_or_404(session, batch_id)
    repo = ResearchBatchRepository(session)
    if body.source_document_id is not None:
        doc = await session.get(SourceDocument, body.source_document_id)
        if doc is None or doc.project_id != b.project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "source_not_found", "message": "Document not in this project"},
            )
        row = await repo.add_document(batch_id, doc.id)
    else:
        assert body.source_audio_id is not None
        aud = await session.get(SourceAudio, body.source_audio_id)
        if aud is None or aud.project_id != b.project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "source_not_found", "message": "Audio not in this project"},
            )
        row = await repo.add_audio(batch_id, aud.id)
    await session.commit()
    await session.refresh(row)
    await invalidate_batch_llm_cache(session, batch_id)
    return ResearchBatchSourceRead.model_validate(row)


@router.post(
    "/{batch_id}/sources/bulk-upload",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def bulk_upload_batch_sources(
    batch_id: UUID,
    session: DbSession,
    ingestion: IngestionServiceDep,
    files: Annotated[list[UploadFile], File(description="Interview files (audio or text)")],
    metadata_json: str = Form(default="{}"),
    run_analysis: bool = Form(default=False),
    language: str | None = Form(default=None),
    transcription_language: str | None = Form(default=None),
    source_type: SourceType = Form(default=SourceType.UPLOAD),
    invalidate_llm_cache: bool = Form(
        default=True,
        description="Clear cached audience portrait / PR strategy for this batch after upload.",
    ),
) -> BulkUploadResponse:
    b = await _batch_or_404(session, batch_id)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "no_files", "message": "At least one file is required"},
        )
    if len(files) > _MAX_BULK_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "too_many_files",
                "message": f"Maximum {_MAX_BULK_FILES} files per request",
            },
        )
    current_n = len(b.sources)
    if current_n + len(files) > _MAX_BATCH_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "batch_capacity",
                "message": f"Batch would exceed {_MAX_BATCH_SOURCES} sources",
            },
        )
    try:
        meta_base = json.loads(metadata_json) if metadata_json.strip() else {}
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_metadata_json", "message": "metadata_json must be valid JSON"},
        ) from e
    if not isinstance(meta_base, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_metadata_json", "message": "metadata_json must be a JSON object"},
        )

    repo = ResearchBatchRepository(session)
    created: list[BulkUploadResultItem] = []
    pipeline_task_ids: list[str] = []
    sort_base = int(current_n)
    proc_status = (
        BatchSourceProcessingStatus.PENDING.value
        if run_analysis
        else BatchSourceProcessingStatus.IDLE.value
    )
    multi_iv = bool(getattr(b, "single_file_multi_interview_mode", True))

    for i, up in enumerate(files):
        fname = up.filename or "upload"
        ord_i = sort_base + i
        try:
            if is_audio_upload(fname, up.content_type):
                audio = await ingestion.upload_audio_file_stream(
                    b.project_id,
                    upload_file=up,
                    mime_type=up.content_type,
                    language=language,
                    transcription_language=transcription_language,
                    source_type=source_type,
                    extra_metadata=dict(meta_base),
                )
                row = await repo.add_audio(
                    batch_id,
                    audio.id,
                    sort_order=ord_i,
                    processing_status=proc_status,
                )
                audio.metadata_json = merge_batch_analysis_metadata(
                    dict(audio.metadata_json or {}),
                    batch_id=batch_id,
                    batch_source_row_id=row.id,
                    single_file_multi_interview_mode=multi_iv,
                )
                kind: str = "audio"
                sid_doc = None
                sid_audio = audio.id
            else:
                data = await up.read()
                doc = await ingestion.upload_text_file(
                    b.project_id,
                    filename=fname,
                    content=data,
                    mime_type=up.content_type,
                    source_type=source_type,
                    extra_metadata=dict(meta_base),
                )
                row = await repo.add_document(
                    batch_id,
                    doc.id,
                    sort_order=ord_i,
                    processing_status=proc_status,
                )
                doc.metadata_json = merge_batch_analysis_metadata(
                    dict(doc.metadata_json or {}),
                    batch_id=batch_id,
                    batch_source_row_id=row.id,
                    single_file_multi_interview_mode=multi_iv,
                )
                kind = "document"
                sid_doc = doc.id
                sid_audio = None
        except ValueError as e:
            code = str(e)
            if code == "project_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "project_not_found", "message": "Project not found"},
                ) from e
            if code in DOCX_ERROR_CODES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": code, "message": DOCX_ERROR_MESSAGES_EN.get(code, code)},
                ) from e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ingestion_failed", "message": str(e)},
            ) from e

        await session.commit()
        await session.refresh(row)
        created.append(
            BulkUploadResultItem(
                source_kind=kind,  # type: ignore[arg-type]
                source_row_id=row.id,
                source_document_id=sid_doc,
                source_audio_id=sid_audio,
            )
        )

    if created and invalidate_llm_cache:
        try:
            await invalidate_batch_llm_cache(session, batch_id)
        except Exception:
            logger.exception(
                "bulk_upload_batch_sources: invalidate_batch_llm_cache failed batch_id=%s",
                batch_id,
            )
            await session.rollback()

    if run_analysis and created:
        try:
            q = process_batch_processing_queue.delay(str(batch_id))
            pipeline_task_ids.append(str(q.id))
        except Exception:
            logger.exception(
                "bulk_upload_batch_sources: failed to enqueue process_batch_processing_queue "
                "(check REDIS_URL / CELERY_BROKER_URL and that Redis is reachable) batch_id=%s",
                batch_id,
            )

    return BulkUploadResponse(created=created, pipeline_task_ids=pipeline_task_ids)


@router.post(
    "/{batch_id}/documents/recover-pipeline",
    response_model=BatchDocumentPipelineRecoverResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}},
)
async def recover_batch_document_pipeline(batch_id: UUID, session: DbSession) -> BatchDocumentPipelineRecoverResponse:
    """Re-queue chunk+extract for documents stuck in uploaded/chunking/failed states."""
    await _batch_or_404(session, batch_id)
    queued, skipped = await list_batch_documents_needing_recovery(session, batch_id)
    task_ids: list[str] = []
    if queued:
        stmt = select(ResearchBatchSource).where(
            ResearchBatchSource.batch_id == batch_id,
            ResearchBatchSource.source_document_id.in_(queued),
        )
        rows = list((await session.scalars(stmt)).all())
        for row in rows:
            row.processing_status = BatchSourceProcessingStatus.PENDING.value
            row.last_error = None
        t = process_batch_processing_queue.delay(str(batch_id))
        task_ids.append(str(t.id))
    await session.commit()
    return BatchDocumentPipelineRecoverResponse(
        queued_document_ids=queued,
        skipped_document_ids=skipped,
        pipeline_task_ids=task_ids,
    )


@router.delete(
    "/{batch_id}/sources/{source_row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def remove_batch_source(batch_id: UUID, source_row_id: UUID, session: DbSession) -> Response:
    repo = ResearchBatchRepository(session)
    ok = await repo.delete_source_row(batch_id, source_row_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_source_not_found", "message": "Source row not found"},
        )
    await session.commit()
    await invalidate_batch_llm_cache(session, batch_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{batch_id}/report/generate",
    response_model=ProcessingTaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}},
)
async def queue_batch_report(
    batch_id: UUID,
    session: DbSession,
    body: BatchReportGenerateRequest | None = Body(default=None),
) -> ProcessingTaskQueued:
    b = await _batch_or_404(session, batch_id)
    opts = body or BatchReportGenerateRequest()
    task = generate_batch_research_report.delay(
        str(b.project_id),
        str(batch_id),
        output_language=opts.output_language,
    )
    return ProcessingTaskQueued(task_id=str(task.id), status="queued")


@router.get(
    "/{batch_id}/export/excel",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def export_batch_excel(batch_id: UUID, session: DbSession) -> Response:
    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    repo = ResearchReportRepository(session)
    row = await repo.get_latest_for_batch(batch_id)
    try:
        assert_report_exportable(row)
    except ValueError as e:
        code = str(e)
        if code == "report_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "report_not_found", "message": "No batch report to export"},
            ) from e
        if code == "report_not_ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "report_not_ready", "message": "Report not ready"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "report_export_failed", "message": code},
        ) from e
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "No batch report to export"},
        )
    payload = build_research_report_excel_bytes(proj, row)
    stem = export_filename_stem(str(batch_id))
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.xlsx"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get(
    "/{batch_id}/export/ppt",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def export_batch_ppt(batch_id: UUID, session: DbSession) -> Response:
    b = await _batch_or_404(session, batch_id)
    proj = await session.get(Project, b.project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project_not_found", "message": "Project not found"},
        )
    repo = ResearchReportRepository(session)
    row = await repo.get_latest_for_batch(batch_id)
    try:
        assert_report_exportable(row)
    except ValueError as e:
        code = str(e)
        if code == "report_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "report_not_found", "message": "No batch report to export"},
            ) from e
        if code == "report_not_ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "report_not_ready", "message": "Report not ready"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "report_export_failed", "message": code},
        ) from e
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "No batch report to export"},
        )
    payload = build_research_report_pptx_bytes(proj, row)
    stem = export_filename_stem(str(batch_id))
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.pptx"',
            "Content-Length": str(len(payload)),
        },
    )
