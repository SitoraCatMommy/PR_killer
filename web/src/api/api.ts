import { apiJson, buildQuery } from './client';
import type {
  DashboardAggregateRead,
  EntityListResponse,
  EntityType,
  HealthResponse,
  InsightRead,
  MaterialCreate,
  MaterialRead,
  MessageResponse,
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
