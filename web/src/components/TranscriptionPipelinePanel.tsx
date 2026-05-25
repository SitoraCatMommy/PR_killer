import type { AudioPipelineProgressRead } from '../api/types';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { ru } from '../i18n/ru';
import { Check, Loader2 } from 'lucide-react';

const PIPELINE_ORDER = ['uploaded', 'splitting', 'transcribing', 'merging', 'ready'] as const;

function pipelineStepIndex(overall: string): number {
  const o = overall.toLowerCase();
  const i = PIPELINE_ORDER.indexOf(o as (typeof PIPELINE_ORDER)[number]);
  return i >= 0 ? i : 0;
}

function transcriptBadgeVariant(
  status: string | undefined,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (!status) return 'outline';
  const s = status.toLowerCase();
  if (s === 'completed') return 'default';
  if (s === 'failed' || s === 'cancelled') return 'destructive';
  if (s === 'running' || s === 'queued' || s === 'pending') return 'secondary';
  return 'outline';
}

type Props = {
  progress: AudioPipelineProgressRead | undefined;
  progressLoading: boolean;
  transcriptStatus: string | undefined;
  onRetry?: () => void;
  retryPending?: boolean;
};

export function TranscriptionPipelinePanel({
  progress,
  progressLoading,
  transcriptStatus,
  onRetry,
  retryPending,
}: Props) {
  const overall = (progress?.overall_status ?? 'uploaded').toLowerCase();
  const failed = overall === 'failed';
  const ready = overall === 'ready';
  const activeIdx = failed ? -1 : pipelineStepIndex(overall);
  const total = progress?.total_chunks ?? 0;
  const done = progress?.done_chunks ?? 0;
  const failedSeg = progress?.failed_chunks ?? 0;
  const chunkPct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const showIndeterminateChunks = !failed && !ready && total === 0 && overall !== 'uploaded';

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">{ru.pipeline.title}</span>
        {progressLoading && !progress ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
        ) : null}
        {progress ? (
          <Badge variant={failed ? 'destructive' : ready ? 'default' : 'secondary'} className="text-xs">
            {ru.pipeline.audioStage(progress.current_stage || overall)}
          </Badge>
        ) : null}
      </div>

      <ol className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        {PIPELINE_ORDER.map((key, idx) => {
          const isDone = !failed && activeIdx > idx;
          const isActive = !failed && activeIdx === idx;
          const isPending = !failed && activeIdx < idx;
          return (
            <li
              key={key}
              className={cn(
                'flex min-w-0 flex-1 items-start gap-2 rounded-md border px-2 py-2 text-xs sm:max-w-[140px]',
                isActive && 'border-primary/50 bg-primary/5',
                isDone && 'border-border/60 bg-muted/30',
                isPending && 'border-transparent bg-muted/10 text-muted-foreground',
                failed && 'border-destructive/25 bg-destructive/5 text-muted-foreground',
              )}
            >
              <span className="mt-0.5 shrink-0">
                {isDone ? (
                  <Check className="size-4 text-primary" aria-hidden />
                ) : isActive ? (
                  <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
                ) : (
                  <span className="flex size-4 items-center justify-center rounded-full border border-border text-[10px]">
                    {idx + 1}
                  </span>
                )}
              </span>
              <span className="leading-snug">{ru.pipeline.audioStage(key)}</span>
            </li>
          );
        })}
      </ol>

      {total > 0 ? (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{ru.pipeline.chunksLabel}</span>
            <span>
              {ru.pipeline.chunksLine(done, total, failedSeg)}
            </span>
          </div>
          <Progress value={chunkPct} />
        </div>
      ) : showIndeterminateChunks ? (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">{ru.pipeline.chunksPreparing}</p>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/60" />
          </div>
        </div>
      ) : null}

      {transcriptStatus ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">{ru.pipeline.transcriptLineLabel}</span>
          <Badge variant={transcriptBadgeVariant(transcriptStatus)} className="text-xs">
            {ru.pipeline.transcriptStatus(transcriptStatus)}
          </Badge>
        </div>
      ) : null}

      {failed && progress?.last_error ? (
        <Alert variant="destructive">
          <AlertTitle>{ru.pipeline.errorTitle}</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap wrap-break-word text-sm">
            {progress.last_error}
          </AlertDescription>
        </Alert>
      ) : null}

      {failed && onRetry ? (
        <Button type="button" variant="secondary" size="sm" disabled={retryPending} onClick={onRetry}>
          {retryPending ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" aria-hidden />
              {ru.pipeline.retrying}
            </>
          ) : (
            ru.common.retry
          )}
        </Button>
      ) : null}
    </div>
  );
}
