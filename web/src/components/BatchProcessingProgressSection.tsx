import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type {
  BatchAudioPipelineItemRead,
  BatchAudioPipelineSummary,
  BatchDataReadinessDiagnostics,
  DocumentPipelineRow,
} from '../api/types';
import type { ResearchBatchSourceRow } from '../api/api';
import { ru } from '../i18n/ru';
import { cn } from '@/lib/utils';

function docPhase(pipeline: Record<string, unknown> | undefined): string {
  const p = pipeline ?? {};
  const raw = (p.phase ?? p.stage ?? '') as string;
  return String(raw || '').trim().toLowerCase();
}

function docExtractionError(pipeline: Record<string, unknown> | undefined): string | null {
  const p = pipeline ?? {};
  const ext = p.extraction;
  if (!ext || typeof ext !== 'object') return null;
  const st = String((ext as { status?: string }).status || '').toLowerCase();
  if (st === 'chunk_failed' || st === 'extraction_failed') {
    const msg = (ext as { message?: string }).message;
    return typeof msg === 'string' && msg.trim() ? msg.trim() : ru.batch.processingDocExtractionFailedShort;
  }
  return null;
}

function docProgressApprox(phase: string, pipeline: Record<string, unknown>): number {
  if (!phase || phase === 'uploaded') return 5;
  if (phase === 'parsed') return 25;
  if (phase === 'chunked') return 60;
  if (['extracted', 'synthesized', 'done'].includes(phase)) return 100;
  const n = Number(pipeline.chunk_count);
  if (Number.isFinite(n) && n > 0) return 55;
  return 15;
}

function queueRowMeta(
  rows: ResearchBatchSourceRow[] | undefined,
  sourceDocumentId: string | null | undefined,
  sourceAudioId: string | null | undefined,
): { status: string; lastError: string | null } | null {
  if (!rows?.length) return null;
  const hit = rows.find((r) => {
    if (sourceDocumentId && r.source_document_id === sourceDocumentId) return true;
    if (sourceAudioId && r.source_audio_id === sourceAudioId) return true;
    return false;
  });
  if (!hit) return null;
  const status = String(hit.processing_status || 'idle').toLowerCase();
  const lastError = typeof hit.last_error === 'string' && hit.last_error.trim() ? hit.last_error : null;
  return { status, lastError };
}

function QueueStatusBadge({ status, lastError }: { status: string; lastError: string | null }) {
  const s = (status || 'idle').toLowerCase();
  let label: string = ru.batch.processingQueueIdle;
  let variant: 'default' | 'secondary' | 'destructive' | 'outline' = 'outline';
  if (s === 'pending') {
    label = ru.batch.processingQueuePending;
    variant = 'secondary';
  } else if (s === 'processing') {
    label = ru.batch.processingQueueProcessing;
    variant = 'secondary';
  } else if (s === 'completed') {
    label = ru.batch.processingQueueCompleted;
    variant = 'default';
  } else if (s === 'failed') {
    label = ru.batch.processingQueueFailed;
    variant = 'destructive';
  }
  return (
    <div className="flex items-center gap-1">
      {s === 'processing' ? <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" /> : null}
      <Badge variant={variant} className="text-[10px]" title={lastError || undefined}>
        {label}
      </Badge>
    </div>
  );
}

type Props = {
  hasBatchSources: boolean;
  audioPending: boolean;
  audioError: unknown;
  summary: BatchAudioPipelineSummary | null | undefined;
  audioItems: BatchAudioPipelineItemRead[];
  diagnostics?: BatchDataReadinessDiagnostics | null;
  documentPipelines?: DocumentPipelineRow[] | null;
  /** Per-source queue state from GET /batches/:id (``processing_status``). */
  batchSourceRows?: ResearchBatchSourceRow[] | null;
  /** True while batch has pending/processing queue rows (Celery drain). */
  queueActive?: boolean;
  dashboardPending: boolean;
  onRefreshNow: () => void | Promise<void>;
  refreshing: boolean;
};

export function BatchProcessingProgressSection({
  hasBatchSources,
  audioPending,
  audioError,
  summary,
  audioItems,
  diagnostics,
  documentPipelines,
  batchSourceRows,
  queueActive,
  dashboardPending,
  onRefreshNow,
  refreshing,
}: Props) {
  if (!hasBatchSources) return null;

  const totalInt = summary?.total_interviews ?? diagnostics?.interviews_total ?? 0;
  const procInt = summary?.processed_interviews ?? diagnostics?.interviews_processed ?? 0;
  const errCount = summary?.errors_count ?? 0;
  const audioFailed = summary?.failed ?? 0;
  const hasErrors = errCount > 0 || audioFailed > 0;

  const audioInFlight = audioItems.some((it) => {
    const st = (it.overall_status || '').toLowerCase();
    return st !== 'ready' && st !== 'failed';
  });
  const pipelinesRunning = Boolean(diagnostics?.pipelines_still_running);
  const interviewsIncomplete = totalInt > 0 && procInt < totalInt;
  const showGlobalBarReason =
    hasErrors ||
    pipelinesRunning ||
    (summary?.in_progress ?? 0) > 0 ||
    audioInFlight ||
    interviewsIncomplete;

  const dataLoading = audioPending || dashboardPending;

  const waitingForPipelineStart =
    !dataLoading &&
    !showGlobalBarReason &&
    !hasErrors &&
    (diagnostics?.chunks_total ?? 0) < 1 &&
    !pipelinesRunning &&
    (diagnostics?.interviews_processed ?? 0) < 1;

  const showSection =
    showGlobalBarReason || dataLoading || waitingForPipelineStart || Boolean(queueActive);
  if (!showSection) return null;

  const percent =
    totalInt > 0 ? Math.min(100, Math.max(0, Math.round((procInt / totalInt) * 100))) : 0;

  let statusBadge: 'errors' | 'done' | 'progress' | 'waiting' = 'progress';
  if (hasErrors) statusBadge = 'errors';
  else if (waitingForPipelineStart) statusBadge = 'waiting';
  else if (totalInt > 0 && procInt >= totalInt && !pipelinesRunning && !audioInFlight) statusBadge = 'done';

  const docRowsFiltered = (documentPipelines ?? []).filter((r) => Boolean(docPhase(r.pipeline)));

  return (
    <div className="space-y-4 rounded-lg border border-border/80 bg-muted/20 p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-base font-semibold tracking-tight">{ru.batch.processingBlockTitle}</h3>
          <p className="text-sm text-muted-foreground">
            {ru.batch.processingBlockSubtitle(procInt, totalInt, errCount)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {statusBadge === 'errors' ? (
            <Badge variant="destructive">{ru.batch.processingStatusErrors}</Badge>
          ) : statusBadge === 'done' ? (
            <Badge className="bg-emerald-600 hover:bg-emerald-600">{ru.batch.processingStatusDone}</Badge>
          ) : statusBadge === 'waiting' ? (
            <Badge variant="outline">{ru.batch.processingStatusWaiting}</Badge>
          ) : (
            <Badge variant="secondary">{ru.batch.processingStatusInProgress}</Badge>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            disabled={refreshing}
            onClick={() => void onRefreshNow()}
          >
            {refreshing ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            {ru.batch.processingRefreshNow}
          </Button>
        </div>
      </div>

      {dataLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-3 w-full rounded-full" />
          <Skeleton className="h-4 w-2/3" />
          <p className="text-xs text-muted-foreground">{ru.batch.processingLoadingHint}</p>
        </div>
      ) : waitingForPipelineStart ? (
        <p className="text-sm text-muted-foreground">{ru.batch.processingWaitingStart}</p>
      ) : (
        <>
          <div className="space-y-2">
            <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="text-xs tabular-nums text-muted-foreground">{percent}%</p>
          </div>

          {(audioItems.length > 0 || docRowsFiltered.length > 0) && (
            <div className="overflow-x-auto rounded-md border bg-background/80">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[min(220px,32vw)]">{ru.batch.processingColFile}</TableHead>
                    <TableHead>{ru.batch.processingColQueue}</TableHead>
                    <TableHead>{ru.batch.processingColStage}</TableHead>
                    <TableHead className="tabular-nums">{ru.batch.processingColChunks}</TableHead>
                    <TableHead className="min-w-[120px]">{ru.batch.processingColProgress}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {audioItems.map((it) => {
                    const total = Math.max(0, it.total_chunks);
                    const done = Math.max(0, it.done_chunks);
                    const pct =
                      typeof it.progress_percent === 'number'
                        ? it.progress_percent
                        : total > 0
                          ? Math.min(100, Math.round((100 * done) / total))
                          : 0;
                    const stage = (it.pipeline_stage || it.current_stage || 'unknown').toString();
                    const failed = (it.overall_status || '').toLowerCase() === 'failed';
                    const qm = queueRowMeta(batchSourceRows ?? undefined, null, it.source_audio_id);
                    return (
                      <TableRow key={it.source_audio_id}>
                        <TableCell className="max-w-[220px] truncate text-xs font-medium">
                          {it.filename || it.source_audio_id}
                        </TableCell>
                        <TableCell className="text-xs">
                          {qm ? (
                            <QueueStatusBadge status={qm.status} lastError={qm.lastError} />
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs">
                          <span className="text-muted-foreground">{ru.batch.kindAudio}</span>
                          {' · '}
                          {ru.pipeline.audioStage(stage)}
                          {failed ? (
                            <Badge variant="destructive" className="ml-2 align-middle text-[10px]">
                              {ru.batch.processingFileFailed}
                            </Badge>
                          ) : null}
                        </TableCell>
                        <TableCell className="tabular-nums text-xs text-muted-foreground">
                          {ru.batch.audioPipelineChunksBatch(done, total, it.failed_chunks)}
                        </TableCell>
                        <TableCell>
                          <div className="flex min-w-[100px] flex-col gap-1">
                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                              <div
                                className={cn(
                                  'h-full rounded-full transition-[width]',
                                  failed ? 'bg-destructive' : 'bg-primary',
                                )}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
                            {it.last_error ? (
                              <span className="text-[11px] text-destructive">{it.last_error}</span>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {docRowsFiltered.map((row) => {
                    const phase = docPhase(row.pipeline);
                    const extErr = docExtractionError(row.pipeline);
                    const failed = Boolean(extErr);
                    const pct = docProgressApprox(phase, row.pipeline);
                    const chunksN =
                      typeof row.pipeline.chunk_count === 'number' ? row.pipeline.chunk_count : null;
                    const qm = queueRowMeta(batchSourceRows ?? undefined, row.source_document_id, null);
                    return (
                      <TableRow key={row.source_document_id}>
                        <TableCell className="max-w-[220px] truncate text-xs font-medium">
                          {row.filename || row.source_document_id}
                        </TableCell>
                        <TableCell className="text-xs">
                          {qm ? (
                            <QueueStatusBadge status={qm.status} lastError={qm.lastError} />
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs">
                          <span className="text-muted-foreground">{ru.batch.kindDocument}</span>
                          {' · '}
                          {ru.batch.documentPipelinePhase(phase || 'unknown')}
                          {failed ? (
                            <Badge variant="destructive" className="ml-2 align-middle text-[10px]">
                              {ru.batch.processingFileFailed}
                            </Badge>
                          ) : null}
                        </TableCell>
                        <TableCell className="tabular-nums text-xs text-muted-foreground">
                          {chunksN != null ? String(chunksN) : '—'}
                        </TableCell>
                        <TableCell>
                          <div className="flex min-w-[100px] flex-col gap-1">
                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                              <div
                                className={cn(
                                  'h-full rounded-full transition-[width]',
                                  failed ? 'bg-destructive' : 'bg-primary',
                                )}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
                            {extErr ? (
                              <span className="text-[11px] text-destructive">{extErr}</span>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}

      {audioError ? (
        <p className="text-xs text-destructive">
          {(audioError as Error)?.message || ru.common.errorGeneric}
        </p>
      ) : null}
    </div>
  );
}

export function BatchAiProcessingGateCard() {
  const scrollToProgress = () => {
    requestAnimationFrame(() =>
      document
        .getElementById('batch-evidence-dashboard')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    );
  };
  return (
    <div
      className="rounded-md border border-amber-500/35 bg-amber-500/5 p-4 text-sm space-y-2"
      role="status"
    >
      <p className="font-medium text-foreground">{ru.batch.processingAiGateTitle}</p>
      <p className="text-muted-foreground leading-relaxed">{ru.batch.processingAiGateBody}</p>
      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={scrollToProgress}>
        {ru.batch.processingScrollToProgress}
      </Button>
    </div>
  );
}
