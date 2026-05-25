from datetime import datetime
from typing import Any, Literal

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.decision_layer import DecisionAlertItem, ImpactEffortMatrixItem, PriorityActionItem
from app.schemas.pagination import PaginatedMeta


class ResearchBatchCreate(BaseModel):
    name: str = Field(max_length=512)
    description: str | None = None


class ResearchBatchUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=512)
    description: str | None = None
    output_language: str | None = Field(
        default=None,
        description="ru|uz|en — optional override for this batch; null clears override",
    )
    single_file_multi_interview_mode: bool | None = Field(
        default=None,
        description="When true (default), one uploaded file may contain many interviews; counts use interview_units.",
    )


class ResearchBatchSourceRead(BaseModel):
    """Batch junction row (minimal; use `ResearchBatchSourceItemRead` in batch detail)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    source_document_id: UUID | None
    source_audio_id: UUID | None
    created_at: datetime


class ResearchBatchSourceItemRead(BaseModel):
    """Junction row plus interview filename and flexible `metadata_json` from the source surface."""

    id: UUID
    batch_id: UUID
    source_document_id: UUID | None
    source_audio_id: UUID | None
    created_at: datetime
    processing_status: str = "idle"
    sort_order: int = 0
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source_kind: Literal["document", "audio"]
    filename: str = ""
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ResearchBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None
    output_language: str | None = None
    single_file_multi_interview_mode: bool = True
    created_at: datetime
    updated_at: datetime


class ResearchBatchQueueSummary(BaseModel):
    """Per-batch source queue counts (``research_batch_sources.processing_status``)."""

    idle: int = 0
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    currently_processing_row_id: UUID | None = None


class ResearchBatchDetailRead(ResearchBatchRead):
    sources: list[ResearchBatchSourceItemRead] = Field(default_factory=list)
    queue_summary: ResearchBatchQueueSummary


class ResearchBatchListResponse(BaseModel):
    items: list[ResearchBatchRead]
    meta: PaginatedMeta


class BatchSourceAddRequest(BaseModel):
    source_document_id: UUID | None = None
    source_audio_id: UUID | None = None

    def surface(self) -> Literal["document", "audio"]:
        d = self.source_document_id is not None
        a = self.source_audio_id is not None
        if d and not a:
            return "document"
        if a and not d:
            return "audio"
        raise ValueError("exactly_one_source")


class BatchReportGenerateRequest(BaseModel):
    output_language: str | None = Field(default=None, description="ru|uz|en — optional override for project")


class BatchDashboardResponse(BaseModel):
    """Structured dashboard payload for simple charts (no raw entity dumps)."""

    model_config = ConfigDict(extra="allow")

    batch: dict[str, Any]
    topics_pie: list[dict[str, Any]]
    problems_bar: list[dict[str, Any]]
    risks_bar: list[dict[str, Any]]
    word_frequency: list[dict[str, Any]]
    sentiment: dict[str, Any]
    top_patterns: list[dict[str, Any]]
    top_insights: list[dict[str, Any]]
    audience_snapshot: dict[str, Any] = Field(default_factory=dict)
    group_by: str | None = None
    segment_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Echo of dashboard query filters (parity with export endpoints).",
    )


class BulkUploadResultItem(BaseModel):
    source_kind: Literal["document", "audio"]
    source_row_id: UUID
    source_document_id: UUID | None
    source_audio_id: UUID | None


class BulkUploadResponse(BaseModel):
    created: list[BulkUploadResultItem]
    pipeline_task_ids: list[str] = Field(default_factory=list)


class BatchDocumentPipelineRecoverResponse(BaseModel):
    """Queued Celery tasks to re-run chunk+extract for stuck documents in a batch."""

    queued_document_ids: list[UUID]
    skipped_document_ids: list[UUID] = Field(default_factory=list)
    pipeline_task_ids: list[str] = Field(default_factory=list)


class InterviewUnitRead(BaseModel):
    """Logical interview inside one source document."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_document_id: UUID
    unit_index: int
    speaker: str | None = None
    language: str | None = None
    language_confidence: float | None = None
    split_method: str = ""
    text_preview: str = Field(default="", description="First ~240 chars of unit text")


class BatchInterviewUnitsResponse(BaseModel):
    items: list[InterviewUnitRead]


class SampleQuoteItem(BaseModel):
    type: str = ""
    title: str = ""
    text: str = ""
    entity_id: str | None = None
    source_document_id: str | None = None
    source_audio_id: str | None = None
    transcript_id: str | None = None
    chunk_id: str | None = None


class PRGroundingEvidenceItem(BaseModel):
    """Single quote with stable source pointers."""

    quote: str = ""
    entity_id: str | None = None
    source_document_id: str | None = None
    source_audio_id: str | None = None
    transcript_id: str | None = None
    chunk_id: str | None = None
    segment: dict[str, Any] = Field(default_factory=dict)


class PRGroundingRow(BaseModel):
    """One PR line with 2–5 evidence items (enforced in builder)."""

    insight_id: str = Field(default="", description="Stable id for traceability / based_on links.")
    insight: str = ""
    insight_kind: str = ""
    evidence: list[PRGroundingEvidenceItem] = Field(default_factory=list)
    insight_type: str = ""


class EvidenceInsightQuote(BaseModel):
    quote: str = ""
    transcript_id: str = ""
    chunk_id: str = ""
    segment: dict[str, Any] = Field(default_factory=dict)
    source_document_id: str | None = None
    source_audio_id: str | None = None
    entity_id: str | None = None


class EvidenceDrivenInsight(BaseModel):
    """Verifiable insight: must ship with 2–5 quotes and trace ids."""

    insight_id: str
    insight: str
    count: int = Field(ge=1)
    coverage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    sentiment: str = ""
    evidence: list[EvidenceInsightQuote] = Field(default_factory=list, max_length=5)
    source_ids: list[str] = Field(default_factory=list)
    transcript_ids: list[str] = Field(default_factory=list)


class InsufficientDataPayload(BaseModel):
    status: Literal["insufficient_data"] = "insufficient_data"
    message: str = ""
    missing: list[str] = Field(default_factory=list)


class PRActionCardItem(BaseModel):
    """Decision-ready action: grounded evidence refs; channel optional (deprecated)."""

    action: str = ""
    for_segment: str = "all"
    channel: str = Field(default="", description="Deprecated — keep empty for simplified PR output.")
    message: str = ""
    expected_effect: str = ""
    risk_if_ignored: str = ""
    evidence_refs: list[PRGroundingEvidenceItem] = Field(default_factory=list)
    evidence_status: Literal["ok", "insufficient_evidence"] = "insufficient_evidence"
    based_on: list[str] = Field(
        default_factory=list,
        description="EvidenceDrivenInsight.insight_id list (filled server-side when possible).",
    )


class PRRiskAlertItem(BaseModel):
    """PR risk alert with index, severity, trend, and traceable refs."""

    risk_index: int = Field(default=0, ge=0, le=100)
    severity: Literal["high", "medium", "low"] = "medium"
    trend: Literal["up", "down", "stable"] = "stable"
    title: str = ""
    evidence_refs: list[PRGroundingEvidenceItem] = Field(default_factory=list)


class MessageLabSegmentReaction(BaseModel):
    segment: str = ""
    reaction: str = ""


class MessageLabAnalyzeResponse(BaseModel):
    """Interactive Message Lab: score + rewrites + segment reactions (or insufficient evidence)."""

    insufficient_evidence: bool = False
    clarity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    trust_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rewrite_variants: list[str] = Field(default_factory=list)
    segment_reactions: list[MessageLabSegmentReaction] = Field(default_factory=list)
    notes: str = ""

    @field_validator("rewrite_variants")
    @classmethod
    def _cap_rewrites(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()][:2]


class MessageLabAnalyzeRequest(BaseModel):
    message: str = Field(max_length=4000)
    output_language: str | None = Field(default=None, description="ru|uz|en")


class AudiencePortraitFields(BaseModel):
    decision_making: str = ""
    fears: str = ""
    trust_drivers: str = ""
    pain_points: str = ""
    language_style: str = ""
    brand_perception: str = ""
    emotional_triggers: str = ""


class AudiencePortraitResponse(BaseModel):
    portrait: AudiencePortraitFields
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Legacy combined confidence; see data_coverage_score",
    )
    data_coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    synthesis_blocked: bool = False
    data_quality_message: str | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)
    portrait_grounding: dict[str, Any] = Field(
        default_factory=dict,
        description="Per field: lists of {insight, evidence:[{quote, entity_id, source ids}]}",
    )
    interview_count: int = 0
    segment_distribution: dict[str, Any] = Field(default_factory=dict)
    evidence_count: int = 0
    segment_coverage: dict[str, Any] = Field(default_factory=dict)
    sample_quotes: list[SampleQuoteItem] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class PRStrategyResponse(BaseModel):
    """Actionable PR plan derived from portrait + batch research signals."""

    dashboard_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="topics/problems/risks/sentiment/interview_count — always before LLM-derived fields.",
    )
    evidence_insights: list[EvidenceDrivenInsight] = Field(
        default_factory=list,
        description="Structured insights with 2–5 quotes each; omitted when insufficient data.",
    )
    insufficient_data: InsufficientDataPayload | None = Field(
        default=None,
        description="When set, LLM synthesis was skipped or produced no grounded insights.",
    )
    data_coverage_pct: int = Field(default=0, ge=0, le=100, description="0–100 integer view of coverage.")
    brand_perception_summary: str = ""
    key_pr_insights: list[str] = Field(default_factory=list)
    reputational_risks: list[str] = Field(default_factory=list)
    communication_gaps: list[str] = Field(default_factory=list)
    recommended_messages: list[str] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)
    media_hooks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    synthesis_blocked: bool = False
    data_quality_message: str | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)
    interview_count: int = 0
    segment_distribution: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    priority_actions: list[PriorityActionItem] = Field(default_factory=list)
    impact_effort_matrix: list[ImpactEffortMatrixItem] = Field(default_factory=list)
    alerts: list[DecisionAlertItem] = Field(default_factory=list)
    evidence_count: int = 0
    segment_coverage: dict[str, Any] = Field(default_factory=dict)
    sample_quotes: list[SampleQuoteItem] = Field(default_factory=list)
    pr_grounding: list[PRGroundingRow] = Field(
        default_factory=list,
        description="Insight-level quotes (2–5 per row); low-evidence lines omitted",
    )
    action_cards: list[PRActionCardItem] = Field(
        default_factory=list,
        description="Primary PR output: action cards with evidence_refs (2–5 when ok).",
    )
    pr_risk_alerts_v2: list[PRRiskAlertItem] = Field(
        default_factory=list,
        description="Structured PR risk alerts (index, severity, trend, evidence_refs).",
    )


class FullReportResponse(BaseModel):
    """Aggregated executive view: summary + cached portrait + strategy + risk/action lists."""

    executive_summary: str = ""
    audience_portrait: AudiencePortraitResponse
    pr_strategy: PRStrategyResponse
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    interview_count: int = 0
    segment_distribution: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    priority_actions: list[PriorityActionItem] = Field(default_factory=list)
    impact_effort_matrix: list[ImpactEffortMatrixItem] = Field(default_factory=list)
    alerts: list[DecisionAlertItem] = Field(default_factory=list)
    evidence_count: int = 0
    segment_coverage: dict[str, Any] = Field(default_factory=dict)
    sample_quotes: list[SampleQuoteItem] = Field(default_factory=list)
    insight_graph: dict[str, Any] = Field(default_factory=dict)
    hierarchical_summary: dict[str, Any] = Field(default_factory=dict)
    pr_risk_alerts: list[dict[str, Any]] = Field(default_factory=list)
    pr_risk_alerts_v2: list[PRRiskAlertItem] = Field(
        default_factory=list,
        description="Structured risk alerts (index, severity, trend, evidence_refs).",
    )
    message_lab: dict[str, Any] = Field(default_factory=dict)
    narrative_builder: dict[str, Any] = Field(default_factory=dict)
    trend_dashboard: dict[str, Any] = Field(default_factory=dict)


class PublicReportSection(BaseModel):
    title: str
    body: str


class PublicReportResponse(BaseModel):
    """Read-only narrative report for unauthenticated clients (no app shell)."""

    batch_id: UUID
    batch_name: str
    executive_summary: str
    sections: list[PublicReportSection]
    risks: list[str]
    recommendations: list[str]
    next_steps: list[str]
    evidence_count: int = 0
    segment_coverage: dict[str, Any] = Field(default_factory=dict)
    sample_quotes: list[SampleQuoteItem] = Field(default_factory=list)
    narrative_markdown: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    dashboard_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="Compact KPIs + PR taxonomy totals + sentiment for public readers.",
    )
    evidence_appendix: dict[str, Any] = Field(
        default_factory=dict,
        description="Traceability sample + PR insight rollups for accountability.",
    )


class BatchPublicLinkResponse(BaseModel):
    token: str
    report_path: str = Field(
        default="",
        description="Relative API path for GET public report (prefix depends on API_V1_PREFIX).",
    )


class DemoCreateResponse(BaseModel):
    batch_id: UUID
    project_id: UUID
    public_token: str = ""
    report_path: str = ""


class SegmentCompareSide(BaseModel):
    """One segment slice: dashboard-style frequencies plus short LLM summaries."""

    segment_key: str
    interview_count: int = 0
    topic_frequency: list[dict[str, Any]] = Field(default_factory=list)
    problem_frequency: list[dict[str, Any]] = Field(default_factory=list)
    risk_frequency: list[dict[str, Any]] = Field(default_factory=list)
    sentiment: dict[str, Any] = Field(default_factory=dict)
    top_insights: list[dict[str, Any]] = Field(default_factory=list)
    word_frequency: list[dict[str, Any]] = Field(default_factory=list)
    audience_portrait_summary: str = ""
    pr_strategy_summary: str = ""


class SegmentCompareDifferenceItem(BaseModel):
    dimension: str
    summary: str


class SegmentCompareResponse(BaseModel):
    """Side-by-side segment metrics and heuristic PR-oriented deltas."""

    group_by: str
    segment_a: SegmentCompareSide
    segment_b: SegmentCompareSide
    differences: list[SegmentCompareDifferenceItem] = Field(default_factory=list)
    pr_implications: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    priority_actions: list[PriorityActionItem] = Field(default_factory=list)
    impact_effort_matrix: list[ImpactEffortMatrixItem] = Field(default_factory=list)
    alerts: list[DecisionAlertItem] = Field(default_factory=list)


class BatchCorpusRead(BaseModel):
    """Merged text from all ``text_chunks`` for sources in a research batch (stable source order)."""

    chunk_count: int = Field(ge=0, description="Number of text chunks across batch sources.")
    total_character_count: int = Field(ge=0, description="Full merged corpus length before truncation.")
    max_chars_applied: int = Field(ge=0, description="Server cap used for the returned ``text`` field.")
    truncated: bool = Field(description="True when ``total_character_count`` exceeds ``max_chars_applied``.")
    text: str = Field(default="", description="Preview text (may be truncated).")
