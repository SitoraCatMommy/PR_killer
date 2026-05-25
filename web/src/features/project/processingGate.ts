import type { BatchDataReadinessDiagnostics } from '@/api/types';

export type ProjectQueueSummary = {
  idle?: number;
  pending?: number;
  processing?: number;
  completed?: number;
  failed?: number;
};

/** True while project source queue or pipelines must finish before AI-heavy features. */
export function isProjectPipelineIncomplete(params: {
  sourcesLength: number;
  queueSummary: ProjectQueueSummary | null | undefined;
  diagnostics: BatchDataReadinessDiagnostics | null | undefined;
  audioInProgress?: number;
  interviewsTotal?: number;
  interviewsProcessed?: number;
}): boolean {
  if (params.sourcesLength < 1) return false;
  const pending = params.queueSummary?.pending ?? 0;
  const processing = params.queueSummary?.processing ?? 0;
  if (pending > 0 || processing > 0) return true;
  if (params.diagnostics?.pipelines_still_running) return true;
  if ((params.audioInProgress ?? 0) > 0) return true;
  const t = params.interviewsTotal ?? 0;
  const p = params.interviewsProcessed ?? 0;
  if (t > 0 && p < t) return true;
  return false;
}
