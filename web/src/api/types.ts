import type { components } from './schema';

export type Schemas = components['schemas'];

export type HealthResponse = Schemas['HealthResponse'];
export type ProjectRead = Schemas['ProjectRead'] & {
  /** Present once OpenAPI schema includes `output_language`. */
  output_language?: string | null;
};
export type ProjectCreate = Schemas['ProjectCreate'];
export type ProjectListResponse = Schemas['ProjectListResponse'];
export type SourceDocumentRead = Schemas['SourceDocumentRead'];
export type SourceAudioRead = Schemas['SourceAudioRead'];
export type UnifiedSourcesResponse = Schemas['UnifiedSourcesResponse'];
export type SourceDocumentDetailRead = Schemas['SourceDocumentDetailRead'];
export type SourceAudioDetailRead = Schemas['SourceAudioDetailRead'];
/** Text chunk from document/audio/transcript split (GET /sources/documents/{id}/chunks). */
export type TextChunkRead = {
  id: string;
  project_id: string;
  source_document_id: string | null;
  source_audio_id: string | null;
  transcript_id: string | null;
  chunk_index: number;
  text: string;
  token_count: number | null;
  created_at: string;
};
export type RawTextNoteCreate = Schemas['RawTextNoteCreate'];
export type EntityListResponse = Schemas['EntityListResponse'];

/** Research extraction / display types (aligned with backend `EntityType`). */
export type EntityType =
  | 'problem'
  | 'pain_point'
  | 'user_need'
  | 'behavior_pattern'
  | 'trust_issue'
  | 'adoption_barrier'
  | 'risk'
  | 'hypothesis'
  | 'recommendation'
  | 'opportunity'
  | 'open_question'
  | 'supporting_fact'
  | 'sentiment_signal'
  | 'person'
  | 'organization'
  | 'location'
  | 'date'
  | 'topic'
  | 'claim'
  | 'metric'
  | 'reference'
  | 'custom';

export type ReportStatus = 'draft' | 'generating' | 'ready' | 'failed';

/** Smart report sections persisted alongside structured JSON columns. */
export type ReportExtrasJson = {
  stage?: string;
  error_code?: string;
  error_message?: string;
  talking_points?: string[];
  reputational_risks?: string[];
  communication_gaps?: string[];
  next_steps_pr?: string[];
  infopovody?: string[];
  open_questions?: string[];
  word_analysis?: {
    word_frequency?: Record<string, number>;
    themed_buckets?: Record<string, Record<string, number>>;
    pr_interpretation?: string;
    /** How dominant terms read for audiences and media (PR lens). */
    dominant_lexicon_pr_perception?: string;
    risk_signal_strength?: string;
    trust_vs_risk_balance?: string;
  };
};

export type ResearchReportRead = {
  id: string;
  project_id: string;
  status: ReportStatus;
  title: string;
  description: string | null;
  executive_summary: string;
  key_findings_json: unknown[];
  problems_json: unknown[];
  patterns_json: unknown[];
  risks_json: unknown[];
  hypotheses_json: unknown[];
  recommendations_json: unknown[];
  forecast_json: unknown[];
  next_steps_json: unknown[];
  external_articles_json: unknown[];
  supporting_quotes_json: unknown[];
  report_extras_json?: ReportExtrasJson;
  created_at: string;
  updated_at: string;
};

export type ResearchReportEnvelope = {
  report: ResearchReportRead | null;
};
export type PRAnalysisReadinessSource = {
  source_kind: 'document' | 'audio' | string;
  source_id: string;
  title: string | null;
  processable: boolean;
  chunk_count: number;
  entity_count: number;
  pr_entity_count: number;
  needs_chunking: boolean;
  needs_extraction: boolean;
  low_signal: boolean;
  reason: string | null;
};

export type PRAnalysisReadiness = {
  ready_for_report: boolean;
  blocking_reasons: string[];
  warnings: string[];
  source_count: number;
  processable_document_count: number;
  completed_transcript_audio_count: number;
  chunk_count: number;
  entity_count: number;
  pr_entity_count: number;
  supporting_fact_count: number;
  needs_chunking_count: number;
  needs_extraction_count: number;
  low_signal_source_count: number;
  aggregation_exists: boolean;
  min_pr_entity_count: number;
  sources: PRAnalysisReadinessSource[];
  queue_summary?: {
    idle?: number;
    pending?: number;
    processing?: number;
    completed?: number;
    failed?: number;
    currently_processing?: { kind: string; id: string }[];
  };
};
export type ResearchSummaryRead = Schemas['ResearchSummaryRead'];
export type MaterialRead = Schemas['MaterialRead'];
export type MaterialCreate = Schemas['MaterialCreate'];
export type InsightRead = Schemas['InsightRead'];
export type DashboardAggregateRead = Schemas['DashboardAggregateRead'];
export type MessageResponse = Schemas['MessageResponse'];
export type SourceType = Schemas['SourceType'];

export type BulkUploadItemResult = {
  filename: string;
  status: 'ok' | 'error' | string;
  id?: string | null;
  source_kind?: string | null;
  task_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type BulkUploadResponse = {
  total: number;
  succeeded: number;
  failed: number;
  items: BulkUploadItemResult[];
};

/** Celery queue response (may be absent from older OpenAPI snapshots). */
export type ProcessingTaskQueued = {
  task_id: string;
  status?: string;
};

/** Latest research aggregation snapshot for a project (see backend `ResearchAggregationSnapshotRead`). */
export type ResearchAggregationSnapshotRead = {
  project_id: string;
  snapshot_type: string;
  period_key: string;
  payload_json: Record<string, unknown>;
  created_at: string;
};

export type ResearchAggregationSnapshotResponse = {
  snapshot: ResearchAggregationSnapshotRead | null;
};

// --- Batch / dashboard frontend shapes (backend JSON; keep permissive where needed) ---

export type OutputLanguage = 'ru' | 'uz' | 'en';
export type TranscriptionLanguageOption = 'auto' | 'ru' | 'uz' | 'en';
export type ReportMode = 'pr_audit' | 'audience' | 'messaging';

export type TracedNavRef = {
  kind?: string;
  document_id?: string;
  audio_id?: string;
  transcript_id?: string | null;
  chunk_id?: string | null;
};

export type TracedSourceRef = {
  nav?: TracedNavRef;
  entity_id?: string | null;
  source_document_id?: string | null;
  source_audio_id?: string | null;
  transcript_id?: string | null;
  chunk_id?: string | null;
};

export type TracedLabelRow = {
  label: string;
  count: number;
  pr_signal_type?: string;
  entity_type?: string;
  source_refs: TracedSourceRef[];
};

export type BatchDashboardTraced = {
  topics?: TracedLabelRow[];
  problems?: TracedLabelRow[];
  risks?: TracedLabelRow[];
};

export type PortraitFieldKey =
  | 'decision_making'
  | 'fears'
  | 'trust_drivers'
  | 'pain_points'
  | 'language_style'
  | 'brand_perception'
  | 'emotional_triggers';

export type PortraitGroundingEvidence = {
  quote?: string;
  entity_id?: string | null;
  source_document_id?: string | null;
  source_audio_id?: string | null;
  transcript_id?: string | null;
};

export type PortraitGroundingItem = {
  insight?: string;
  evidence?: PortraitGroundingEvidence[];
};

export type SampleQuoteItem = PortraitGroundingEvidence & {
  title?: string;
};

export type MessageLabAnalyzeResponse = Record<string, unknown>;

export type BatchDataReadinessDiagnostics = {
  pipelines_still_running?: boolean;
  /** Chunks exist but no extracted entities yet (or empty extraction); not the same as pipeline running. */
  entity_extraction_gap?: boolean;
  interviews_total?: number;
  interviews_processed?: number;
  chunks_total?: number;
  visualization_note?: string;
  missing_steps?: string[];
  [key: string]: unknown;
};

export type DashboardSliceRow = { label: string; value: number; pct?: number | null };

export type DocumentPipelineRow = {
  source_document_id: string;
  filename: string;
  pipeline: Record<string, unknown>;
};

export type BatchDashboardData = {
  batch?: { source_count?: number; name?: string; [key: string]: unknown };
  topics_pie?: DashboardSliceRow[];
  problems_bar?: DashboardSliceRow[];
  risks_bar?: DashboardSliceRow[];
  top_insights?: Array<{ text?: string; pr_signal_type?: string; type?: string }>;
  traced?: BatchDashboardTraced;
  segment_breakdown?: Array<{
    segment_key: string;
    entity_count: number;
    topics_pie: DashboardSliceRow[];
    problems_bar: DashboardSliceRow[];
  }>;
  data_readiness_diagnostics?: BatchDataReadinessDiagnostics | null;
  data_quality?: Record<string, unknown> & {
    strict_pr_ready?: boolean;
    can_synthesize_llm?: boolean;
    gates_checklist?: Array<Record<string, unknown>>;
  };
  evidence_dashboard?: Record<string, unknown>;
  audience_snapshot?: Record<string, unknown>;
  filters?: { segment_values?: string[] } & Record<string, unknown>;
  document_pipelines?: DocumentPipelineRow[];
  interview_units?: unknown[];
  word_frequency?: unknown[];
  timeline_series_real?: unknown[];
  sentiment?: unknown;
  top_patterns?: unknown[];
  insight_graph?: unknown;
  pr_insight_rollups?: unknown;
};

export type BatchAudioPipelineItemRead = {
  source_audio_id: string;
  filename?: string | null;
  total_chunks: number;
  done_chunks: number;
  failed_chunks?: number;
  progress_percent?: number;
  overall_status?: string | null;
  pipeline_stage?: string | null;
  current_stage?: string | null;
  last_error?: string | null;
};

export type BatchAudioPipelineSummary = {
  ready?: number;
  total_audios?: number;
  in_progress?: number;
  failed?: number;
  total_interviews?: number | null;
  processed_interviews?: number | null;
  errors_count?: number | null;
};

export type BatchAudioPipelineResponse = {
  summary: BatchAudioPipelineSummary;
  items: BatchAudioPipelineItemRead[];
};

export type AudioPipelineProgressRead = {
  overall_status?: string | null;
  current_stage?: string | null;
  total_chunks?: number;
  done_chunks?: number;
  failed_chunks?: number;
  last_error?: string | null;
};
