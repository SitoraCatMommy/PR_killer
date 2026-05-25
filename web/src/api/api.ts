import { ApiError, apiJson, buildQuery } from './client';
import { getApiBaseUrl } from '../config';
import type {
  BatchAudioPipelineResponse,
  BatchDashboardData,
  AudioPipelineProgressRead,
  BulkUploadResponse,
  DashboardAggregateRead,
  EntityListResponse,
  EntityType,
  HealthResponse,
  InsightRead,
  MaterialCreate,
  MaterialRead,
  MessageResponse,
  PRAnalysisReadiness,
  ProcessingTaskQueued,
  ProjectCreate,
  ProjectListResponse,
  ProjectRead,
  RawTextNoteCreate,
  ResearchAggregationSnapshotResponse,
  ResearchReportEnvelope,
  ResearchSummaryRead,
  SourceAudioDetailRead,
  SourceAudioRead,
  SourceDocumentDetailRead,
  SourceDocumentRead,
  SourceType,
  TextChunkRead,
  UnifiedSourcesResponse,
} from './types';

export async function getHealth(): Promise<HealthResponse> {
  return apiJson<HealthResponse>('/health');
}

export async function getHealthReady(): Promise<{
  status: string;
  redis: boolean;
}> {
  return apiJson('/health/ready');
}

export async function listProjects(
  offset = 0,
  limit = 50,
): Promise<ProjectListResponse> {
  return apiJson<ProjectListResponse>(`/projects${buildQuery({ offset, limit })}`);
}

export async function createProject(body: ProjectCreate): Promise<ProjectRead> {
  return apiJson<ProjectRead>('/projects', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getProject(projectId: string): Promise<ProjectRead> {
  return apiJson<ProjectRead>(`/projects/${projectId}`);
}

export async function deleteProject(projectId: string): Promise<void> {
  return apiJson<void>(`/projects/${projectId}`, { method: 'DELETE' });
}

export async function uploadTextSource(
  projectId: string,
  file: File,
  sourceType: SourceType = 'upload',
): Promise<SourceDocumentRead> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('source_type', sourceType);
  return apiJson<SourceDocumentRead>(`/projects/${projectId}/sources/text/upload`, {
    method: 'POST',
    body: fd,
  });
}

export async function uploadTextSources(
  projectId: string,
  files: File[],
  sourceType: SourceType = 'upload',
): Promise<BulkUploadResponse> {
  const fd = new FormData();
  files.forEach((file) => fd.append('files', file));
  fd.append('source_type', sourceType);
  return apiJson<BulkUploadResponse>(`/projects/${projectId}/sources/text/upload/bulk`, {
    method: 'POST',
    body: fd,
  });
}

export async function uploadAudioSource(
  projectId: string,
  file: File,
  options?: { language?: string; sourceType?: SourceType },
): Promise<SourceAudioRead> {
  const fd = new FormData();
  fd.append('file', file);
  if (options?.language) fd.append('language', options.language);
  fd.append('source_type', options?.sourceType ?? 'upload');
  return apiJson<SourceAudioRead>(`/projects/${projectId}/sources/audio/upload`, {
    method: 'POST',
    body: fd,
  });
}

export async function uploadAudioSources(
  projectId: string,
  files: File[],
  options?: { language?: string; sourceType?: SourceType },
): Promise<BulkUploadResponse> {
  const fd = new FormData();
  files.forEach((file) => fd.append('files', file));
  if (options?.language) fd.append('language', options.language);
  fd.append('source_type', options?.sourceType ?? 'upload');
  return apiJson<BulkUploadResponse>(`/projects/${projectId}/sources/audio/upload/bulk`, {
    method: 'POST',
    body: fd,
  });
}

export async function createRawTextNote(
  projectId: string,
  body: RawTextNoteCreate,
): Promise<SourceDocumentRead> {
  return apiJson<SourceDocumentRead>(`/projects/${projectId}/sources/text/raw`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listProjectSources(
  projectId: string,
  offset = 0,
  limit = 50,
): Promise<UnifiedSourcesResponse> {
  return apiJson<UnifiedSourcesResponse>(
    `/projects/${projectId}/sources${buildQuery({ offset, limit })}`,
  );
}

export async function getSourceDocument(
  sourceDocumentId: string,
): Promise<SourceDocumentDetailRead> {
  return apiJson<SourceDocumentDetailRead>(
    `/sources/documents/${sourceDocumentId}`,
  );
}

export async function listDocumentChunks(
  sourceDocumentId: string,
): Promise<TextChunkRead[]> {
  return apiJson<TextChunkRead[]>(
    `/sources/documents/${sourceDocumentId}/chunks`,
  );
}

export async function getSourceAudio(sourceAudioId: string): Promise<SourceAudioDetailRead> {
  return apiJson<SourceAudioDetailRead>(`/sources/audios/${sourceAudioId}`);
}

export async function queueTranscribeAudio(
  sourceAudioId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(
    `/sources/audios/${sourceAudioId}/transcribe`,
    { method: 'POST' },
  );
}

export async function queueChunkDocument(
  sourceDocumentId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(
    `/sources/documents/${sourceDocumentId}/chunk`,
    { method: 'POST' },
  );
}

export async function queueChunkDocumentSemantic(
  sourceDocumentId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(
    `/sources/documents/${sourceDocumentId}/chunk/semantic`,
    { method: 'POST' },
  );
}

export async function queueChunkTranscript(
  transcriptId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/transcripts/${transcriptId}/chunk`, {
    method: 'POST',
  });
}

export async function queueChunkTranscriptSemantic(
  transcriptId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(
    `/transcripts/${transcriptId}/chunk/semantic`,
    { method: 'POST' },
  );
}

export async function queueExtractDocument(
  sourceDocumentId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(
    `/sources/documents/${sourceDocumentId}/extract`,
    { method: 'POST' },
  );
}

export async function listProjectEntities(
  projectId: string,
  params: {
    offset?: number;
    limit?: number;
    entity_type?: EntityType;
    min_confidence?: number;
    source_document_id?: string;
    source_audio_id?: string;
    transcript_id?: string;
    /** When true, backend includes types hidden by default (e.g. supporting_fact). */
    include_all_types?: boolean;
  } = {},
): Promise<EntityListResponse> {
  const { offset = 0, limit = 50, ...rest } = params;
  return apiJson<EntityListResponse>(
    `/projects/${projectId}/entities${buildQuery({ offset, limit, ...rest })}`,
  );
}

export async function getProjectSummary(
  projectId: string,
): Promise<ResearchSummaryRead> {
  return apiJson<ResearchSummaryRead>(`/projects/${projectId}/summary`);
}

export async function queueProjectAggregate(
  projectId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/projects/${projectId}/aggregate`, {
    method: 'POST',
  });
}

export async function queueGenerateProjectSummary(
  projectId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(
    `/projects/${projectId}/summary/generate`,
    { method: 'POST' },
  );
}

export async function getProjectReport(
  projectId: string,
): Promise<ResearchReportEnvelope> {
  return apiJson<ResearchReportEnvelope>(`/projects/${projectId}/report`);
}

export async function getPRAnalysisReadiness(
  projectId: string,
): Promise<PRAnalysisReadiness> {
  return apiJson<PRAnalysisReadiness>(`/projects/${projectId}/pr-analysis/readiness`);
}

export async function queueGenerateResearchReport(
  projectId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/projects/${projectId}/smart-report/generate`, {
    method: 'POST',
  });
}

/** Удаляет сохранённые отчёты по проекту и ставит в очередь новую генерацию. */
export async function queueRegenerateResearchReport(
  projectId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/projects/${projectId}/report/regenerate`, {
    method: 'POST',
  });
}

export async function getProjectAggregation(
  projectId: string,
): Promise<ResearchAggregationSnapshotResponse> {
  return apiJson<ResearchAggregationSnapshotResponse>(
    `/projects/${projectId}/aggregation`,
  );
}

export async function queueExtractTranscript(
  transcriptId: string,
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/transcripts/${transcriptId}/extract`, {
    method: 'POST',
  });
}

export async function ingestMaterialText(body: MaterialCreate): Promise<MaterialRead> {
  return apiJson<MaterialRead>('/materials/text', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function ingestMaterialAudio(
  file: File,
  options?: { title?: string; source_uri?: string; extra_metadata?: string },
): Promise<MaterialRead> {
  const fd = new FormData();
  fd.append('file', file);
  if (options?.title != null) fd.append('title', options.title);
  if (options?.source_uri != null) fd.append('source_uri', options.source_uri);
  if (options?.extra_metadata != null) fd.append('extra_metadata', options.extra_metadata);
  return apiJson<MaterialRead>('/materials/audio', {
    method: 'POST',
    body: fd,
  });
}

export async function ingestMaterialAudios(
  files: File[],
  options?: { title?: string; source_uri?: string; extra_metadata?: string },
): Promise<BulkUploadResponse> {
  const fd = new FormData();
  files.forEach((file) => fd.append('files', file));
  if (options?.title != null) fd.append('title', options.title);
  if (options?.source_uri != null) fd.append('source_uri', options.source_uri);
  if (options?.extra_metadata != null) fd.append('extra_metadata', options.extra_metadata);
  return apiJson<BulkUploadResponse>('/materials/audio/bulk', {
    method: 'POST',
    body: fd,
  });
}

export async function listMaterials(limit = 50): Promise<MaterialRead[]> {
  return apiJson<MaterialRead[]>(`/materials${buildQuery({ limit })}`);
}

export async function getMaterial(materialId: string): Promise<MaterialRead> {
  return apiJson<MaterialRead>(`/materials/${materialId}`);
}

export async function reprocessMaterial(materialId: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>(`/materials/${materialId}/reprocess`, {
    method: 'POST',
  });
}

export async function listInsights(limit = 100): Promise<InsightRead[]> {
  return apiJson<InsightRead[]>(`/insights${buildQuery({ limit })}`);
}

export async function listDashboardAggregates(): Promise<DashboardAggregateRead[]> {
  return apiJson<DashboardAggregateRead[]>('/dashboard/aggregates');
}

export async function recomputeDashboardAggregates(): Promise<MessageResponse> {
  return apiJson<MessageResponse>('/dashboard/aggregates/recompute', {
    method: 'POST',
  });
}

// --- Research batches & project-wide dashboard ---

export type DashboardQueryOpts = {
  group_by?: string | null;
  segment_key?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  stopwords?: boolean;
  compare_segment_a?: string | null;
  compare_segment_b?: string | null;
};

export function batchDashboardQueryKey(opts: DashboardQueryOpts): string {
  return JSON.stringify(opts);
}

function dashboardQueryRecord(opts: DashboardQueryOpts) {
  return {
    group_by: opts.group_by ?? undefined,
    segment_key: opts.segment_key ?? undefined,
    date_from: opts.date_from ?? undefined,
    date_to: opts.date_to ?? undefined,
    stopwords: opts.stopwords,
    compare_segment_a: opts.compare_segment_a ?? undefined,
    compare_segment_b: opts.compare_segment_b ?? undefined,
  };
}

export type BatchBulkUploadResultItem = {
  source_kind: 'document' | 'audio';
  source_row_id: string;
  source_document_id?: string | null;
  source_audio_id?: string | null;
};

export type BatchBulkUploadResponse = {
  created: BatchBulkUploadResultItem[];
  pipeline_task_ids: string[];
};

export type ResearchBatchRead = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  output_language?: string | null;
  single_file_multi_interview_mode?: boolean;
  created_at: string;
  updated_at: string;
};

export type ResearchBatchQueueSummary = {
  idle: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  currently_processing_row_id?: string | null;
};

export type ResearchBatchSourceRow = {
  id?: string;
  source_kind?: string;
  source_document_id?: string | null;
  source_audio_id?: string | null;
  processing_status?: string;
  last_error?: string | null;
  [key: string]: unknown;
};

export type ResearchBatchDetailRead = ResearchBatchRead & {
  sources: ResearchBatchSourceRow[];
  queue_summary: ResearchBatchQueueSummary;
};

export type ResearchBatchListResponse = {
  items: ResearchBatchRead[];
  meta: { total: number; limit: number; offset: number };
};

async function fetchAttachment(path: string, filename: string): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}${path}`);
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function createProjectBatch(
  projectId: string,
  body: { name: string; description?: string | null },
): Promise<ResearchBatchRead> {
  return apiJson<ResearchBatchRead>(`/projects/${projectId}/batches`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listProjectBatches(
  projectId: string,
  offset = 0,
  limit = 50,
): Promise<ResearchBatchListResponse> {
  return apiJson<ResearchBatchListResponse>(
    `/projects/${projectId}/batches${buildQuery({ offset, limit })}`,
  );
}

export async function getProjectDashboard(
  projectId: string,
  opts: DashboardQueryOpts = {},
): Promise<BatchDashboardData> {
  return apiJson<BatchDashboardData>(
    `/projects/${projectId}/dashboard${buildQuery(dashboardQueryRecord(opts))}`,
  );
}

export async function bulkUploadProjectSources(
  projectId: string,
  files: File[],
  metadataJson: Record<string, unknown>,
  runAnalysis: boolean,
  options?: { invalidateLlmCache?: boolean },
): Promise<BatchBulkUploadResponse> {
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  fd.append('metadata_json', JSON.stringify(metadataJson));
  fd.append('run_analysis', runAnalysis ? 'true' : 'false');
  if (options?.invalidateLlmCache === false) {
    fd.append('invalidate_llm_cache', 'false');
  }
  return apiJson<BatchBulkUploadResponse>(`/projects/${projectId}/sources/bulk-upload`, {
    method: 'POST',
    body: fd,
  });
}

export async function queueProcessProject(projectId: string): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/projects/${projectId}/process`, { method: 'POST' });
}

export type ProjectProcessingQueueResponse = {
  idle: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  currently_processing: { kind: string; id: string }[];
  sources: {
    kind: string;
    id: string;
    filename: string;
    processing_status: string;
    processing_last_error: string | null;
  }[];
};

export async function getProjectProcessingQueue(
  projectId: string,
): Promise<ProjectProcessingQueueResponse> {
  return apiJson<ProjectProcessingQueueResponse>(`/projects/${projectId}/processing-queue`);
}

export async function recoverProjectDocumentPipeline(projectId: string): Promise<{
  queued_document_ids: string[];
  skipped_document_ids: string[];
  pipeline_task_ids: string[];
}> {
  return apiJson(`/projects/${projectId}/documents/recover-pipeline`, { method: 'POST' });
}

export async function getProjectAudiencePortrait(
  projectId: string,
  params: {
    recalculate?: boolean;
    group_by?: string | null;
    segment_value?: string | null;
  } = {},
): Promise<any> {
  return apiJson<any>(
    `/projects/${projectId}/audience-portrait${buildQuery({
      recalculate: params.recalculate,
      group_by: params.group_by ?? undefined,
      segment_value: params.segment_value ?? undefined,
    })}`,
  );
}

export async function getProjectPRStrategy(
  projectId: string,
  params: {
    recalculate?: boolean;
    group_by?: string | null;
    segment_value?: string | null;
  } = {},
): Promise<any> {
  return apiJson<any>(
    `/projects/${projectId}/pr-strategy${buildQuery({
      recalculate: params.recalculate,
      group_by: params.group_by ?? undefined,
      segment_value: params.segment_value ?? undefined,
    })}`,
  );
}

export async function getProjectFullReport(
  projectId: string,
  params: { recalculate?: boolean } = {},
): Promise<any> {
  return apiJson<any>(
    `/projects/${projectId}/full-report${buildQuery({ recalculate: params.recalculate })}`,
  );
}

export async function createProjectPublicLink(projectId: string): Promise<{ token: string; report_path: string }> {
  return apiJson<{ token: string; report_path: string }>(`/projects/${projectId}/public-link`, {
    method: 'POST',
  });
}

export async function getBatch(batchId: string): Promise<ResearchBatchDetailRead> {
  return apiJson<ResearchBatchDetailRead>(`/batches/${batchId}`);
}

export async function patchResearchBatch(
  batchId: string,
  body: Partial<{
    name: string;
    description: string | null;
    output_language: string | null;
    single_file_multi_interview_mode: boolean;
  }>,
): Promise<ResearchBatchRead> {
  return apiJson<ResearchBatchRead>(`/batches/${batchId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function bulkUploadBatchSources(
  batchId: string,
  files: File[],
  metadataJson: Record<string, unknown>,
  runAnalysis: boolean,
  options?: { invalidateLlmCache?: boolean },
): Promise<BatchBulkUploadResponse> {
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  fd.append('metadata_json', JSON.stringify(metadataJson));
  fd.append('run_analysis', runAnalysis ? 'true' : 'false');
  if (options?.invalidateLlmCache === false) {
    fd.append('invalidate_llm_cache', 'false');
  }
  return apiJson<BatchBulkUploadResponse>(`/batches/${batchId}/sources/bulk-upload`, {
    method: 'POST',
    body: fd,
  });
}

export async function addBatchSource(
  batchId: string,
  body: { source_document_id?: string; source_audio_id?: string },
): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>(`/batches/${batchId}/sources`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function removeBatchSource(batchId: string, sourceRowId: string): Promise<void> {
  return apiJson<void>(`/batches/${batchId}/sources/${sourceRowId}`, { method: 'DELETE' });
}

export async function getBatchDashboard(
  batchId: string,
  opts: DashboardQueryOpts = {},
): Promise<BatchDashboardData> {
  return apiJson<BatchDashboardData>(
    `/batches/${batchId}/dashboard${buildQuery(dashboardQueryRecord(opts))}`,
  );
}

export function batchChartSvgUrl(
  batchId: string,
  chartKind: 'topics' | 'problems' | 'risks' | 'pr_taxonomy',
  opts: DashboardQueryOpts,
): string {
  const q = buildQuery(dashboardQueryRecord(opts));
  return `${getApiBaseUrl()}/batches/${batchId}/charts/${chartKind}.svg${q}`;
}

export async function downloadBatchDashboardCsv(
  batchId: string,
  opts: DashboardQueryOpts,
): Promise<void> {
  const q = buildQuery(dashboardQueryRecord(opts));
  await fetchAttachment(`/batches/${batchId}/dashboard-export.csv${q}`, `batch_${batchId}_dashboard.csv`);
}

export async function downloadBatchDashboardPack(
  batchId: string,
  opts: DashboardQueryOpts,
): Promise<void> {
  const q = buildQuery(dashboardQueryRecord(opts));
  await fetchAttachment(`/batches/${batchId}/dashboard-pack.zip${q}`, `batch_${batchId}_pack.zip`);
}

export async function getBatchAudioPipeline(batchId: string): Promise<BatchAudioPipelineResponse> {
  return apiJson<BatchAudioPipelineResponse>(`/batches/${batchId}/audio-pipeline`);
}

export async function getBatchCorpus(batchId: string, maxChars: number): Promise<any> {
  return apiJson<any>(
    `/batches/${batchId}/corpus${buildQuery({ max_chars: maxChars })}`,
  );
}

export async function getBatchInterviewUnits(batchId: string): Promise<{ items: unknown[] }> {
  return apiJson<{ items: unknown[] }>(`/batches/${batchId}/interview-units`);
}

export async function getAudiencePortrait(
  batchId: string,
  params: {
    recalculate?: boolean;
    group_by?: string | null;
    segment_value?: string | null;
  } = {},
): Promise<any> {
  return apiJson<any>(
    `/batches/${batchId}/audience-portrait${buildQuery({
      recalculate: params.recalculate,
      group_by: params.group_by ?? undefined,
      segment_value: params.segment_value ?? undefined,
    })}`,
  );
}

export async function getPRStrategy(
  batchId: string,
  params: {
    recalculate?: boolean;
    group_by?: string | null;
    segment_value?: string | null;
  } = {},
): Promise<any> {
  return apiJson<any>(
    `/batches/${batchId}/pr-strategy${buildQuery({
      recalculate: params.recalculate,
      group_by: params.group_by ?? undefined,
      segment_value: params.segment_value ?? undefined,
    })}`,
  );
}

export async function getBatchFullReport(
  batchId: string,
  params: { recalculate?: boolean } = {},
): Promise<any> {
  return apiJson<any>(
    `/batches/${batchId}/full-report${buildQuery({ recalculate: params.recalculate })}`,
  );
}

export async function getBatchScenarioReport(
  batchId: string,
  mode: 'pr_audit' | 'audience' | 'messaging',
): Promise<any> {
  return apiJson<any>(
    `/batches/${batchId}/report${buildQuery({ mode, recalculate: false })}`,
  );
}

export async function getBatchSegmentCompare(
  batchId: string,
  params: { group_by: string; segment_a: string; segment_b: string },
): Promise<any> {
  return apiJson<any>(
    `/batches/${batchId}/compare${buildQuery({
      group_by: params.group_by,
      segment_a: params.segment_a,
      segment_b: params.segment_b,
    })}`,
  );
}

export async function postMessageLabAnalyze(
  batchId: string,
  body: Record<string, unknown>,
): Promise<any> {
  return apiJson<any>(`/batches/${batchId}/message-lab/analyze`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function queueBatchReportGenerate(
  batchId: string,
  body: { output_language?: string | null },
): Promise<ProcessingTaskQueued> {
  return apiJson<ProcessingTaskQueued>(`/batches/${batchId}/report/generate`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function downloadBatchReportExcel(batchId: string): Promise<void> {
  await fetchAttachment(`/batches/${batchId}/export/excel`, `batch_${batchId}_report.xlsx`);
}

export async function downloadBatchReportPpt(batchId: string): Promise<void> {
  await fetchAttachment(`/batches/${batchId}/export/ppt`, `batch_${batchId}_report.pptx`);
}

export async function getSourceAudioProgress(audioId: string): Promise<AudioPipelineProgressRead> {
  return apiJson<AudioPipelineProgressRead>(`/sources/audios/${audioId}/progress`);
}

export async function promoteAudioTranscript(
  audioId: string,
  body: { target_project_id: string; research_batch_id?: string | null; filename_stem?: string },
): Promise<{ source_document_id: string }> {
  return apiJson<{ source_document_id: string }>(`/sources/audios/${audioId}/transcript/promote`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function downloadAudioTranscriptExport(
  audioId: string,
  format: 'txt' | 'docx' = 'txt',
  downloadFilename?: string,
): Promise<void> {
  const ext = format === 'docx' ? 'docx' : 'txt';
  await fetchAttachment(
    `/sources/audios/${audioId}/transcript/export${buildQuery({ format })}`,
    downloadFilename ?? `transcript_${audioId}.${ext}`,
  );
}
