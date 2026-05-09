import type { components } from './schema';

export type Schemas = components['schemas'];

export type HealthResponse = Schemas['HealthResponse'];
export type ProjectRead = Schemas['ProjectRead'];
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
