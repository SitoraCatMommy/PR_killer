export const qk = {
  health: ['health'] as const,
  healthReady: ['healthReady'] as const,
  projects: (offset: number, limit: number) => ['projects', offset, limit] as const,
  project: (id: string) => ['project', id] as const,
  sources: (projectId: string, offset: number, limit: number) =>
    ['sources', projectId, offset, limit] as const,
  sourceDoc: (id: string) => ['sourceDoc', id] as const,
  sourceAudio: (id: string) => ['sourceAudio', id] as const,
  sourceAudioProgress: (audioId: string) => ['sourceAudioProgress', audioId] as const,
  documentChunks: (documentId: string) => ['documentChunks', documentId] as const,
  entities: (projectId: string, queryKey: string) => ['entities', projectId, queryKey] as const,
  summary: (projectId: string) => ['summary', projectId] as const,
  materials: (limit: number) => ['materials', limit] as const,
  material: (id: string) => ['material', id] as const,
  insights: (limit: number) => ['insights', limit] as const,
  dashboardAggregates: ['dashboardAggregates'] as const,
  projectAggregation: (projectId: string) => ['projectAggregation', projectId] as const,
  projectReport: (projectId: string) => ['projectReport', projectId] as const,
  prAnalysisReadiness: (projectId: string) => ['prAnalysisReadiness', projectId] as const,
  projectProcessingQueue: (projectId: string) => ['projectProcessingQueue', projectId] as const,

  projectBatches: (projectId: string, offset: number, limit: number) =>
    ['projectBatches', projectId, offset, limit] as const,
  projectDashboard: (projectId: string, dashKey: string) =>
    ['projectDashboard', projectId, dashKey] as const,

  batch: (id: string) => ['batch', id] as const,
  batchDashboard: (batchId: string, key: string) => ['batchDashboard', batchId, key] as const,
  batchAudioPipeline: (batchId: string) => ['batchAudioPipeline', batchId] as const,
  batchCorpus: (batchId: string, maxChars: number) => ['batchCorpus', batchId, maxChars] as const,
  batchInterviewUnits: (batchId: string) => ['batchInterviewUnits', batchId] as const,
  batchFullReport: (batchId: string) => ['batchFullReport', batchId] as const,
  batchScenarioReport: (batchId: string, mode: string) =>
    ['batchScenarioReport', batchId, mode] as const,
  batchSegmentCompare: (batchId: string, gb: string, a: string, b: string) =>
    ['batchSegmentCompare', batchId, gb, a, b] as const,
  batchAudiencePortrait: (batchId: string, groupBy: string, segment: string) =>
    ['batchAudiencePortrait', batchId, groupBy, segment] as const,
  batchPrStrategy: (batchId: string, groupBy: string, segment: string) =>
    ['batchPrStrategy', batchId, groupBy, segment] as const,
};
