import type { BatchDataReadinessDiagnostics } from '@/api/types';

/** True while ingestion / transcription / queue must finish before AI-heavy tabs. */
export function isBatchPipelineIncomplete(params: {
  sourcesLength: number;
  queuePending: number;
  queueProcessing: number;
  diagnostics: BatchDataReadinessDiagnostics | null | undefined;
  audioItemsInFlight: boolean;
  audioInProgress: number;
  interviewsTotal: number;
  interviewsProcessed: number;
}): boolean {
  if (params.sourcesLength < 1) return false;
  if (params.queuePending > 0 || params.queueProcessing > 0) return true;
  if (params.diagnostics?.pipelines_still_running) return true;
  if (params.audioItemsInFlight) return true;
  if (params.audioInProgress > 0) return true;
  const t = params.interviewsTotal;
  const p = params.interviewsProcessed;
  if (t > 0 && p < t) return true;
  return false;
}
