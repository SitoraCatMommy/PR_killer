import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  downloadAudioTranscriptExport,
  getSourceAudio,
  getSourceAudioProgress,
  promoteAudioTranscript,
  queueExtractTranscript,
  queueTranscribeAudio,
} from '../api/api';
import { ApiErrorText } from './ApiErrorText';
import { TranscriptionPipelinePanel } from './TranscriptionPipelinePanel';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';
import { Loader2 } from 'lucide-react';

type Props = {
  audioId: string;
  /** `transcription-only`: ASR + текст + TXT/DOCX. `full`: + инсайты + отправка в проект. */
  mode?: 'full' | 'transcription-only';
};

function shouldPollProgress(overall: string | undefined): boolean {
  if (!overall) return true;
  const s = overall.toLowerCase();
  return s !== 'ready' && s !== 'failed';
}

function shouldPollTranscript(ts: string | undefined): boolean {
  if (!ts) return false;
  const s = ts.toLowerCase();
  return s === 'pending' || s === 'queued' || s === 'running';
}

export function AudioTranscriptionWorkflow({ audioId, mode = 'full' }: Props) {
  const qc = useQueryClient();
  const [promoteBatchId, setPromoteBatchId] = useState('');

  const audio = useQuery({
    queryKey: qk.sourceAudio(audioId),
    queryFn: () => getSourceAudio(audioId),
    enabled: !!audioId,
    refetchInterval: (q) => (shouldPollTranscript(q.state.data?.transcript?.status) ? 2500 : false),
  });

  const progress = useQuery({
    queryKey: qk.sourceAudioProgress(audioId),
    queryFn: () => getSourceAudioProgress(audioId),
    enabled: !!audioId,
    refetchInterval: (q) =>
      shouldPollProgress(q.state.data?.overall_status ?? undefined) ? 2500 : false,
  });

  const transcribeMut = useMutation({
    mutationFn: () => queueTranscribeAudio(audioId),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.sourceAudio(audioId) });
      await qc.invalidateQueries({ queryKey: qk.sourceAudioProgress(audioId) });
    },
  });

  const extractTxMut = useMutation({
    mutationFn: (transcriptId: string) => queueExtractTranscript(transcriptId),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.sourceAudio(audioId) });
      await qc.invalidateQueries({ queryKey: qk.sourceAudioProgress(audioId) });
    },
  });

  const promoteMut = useMutation({
    mutationFn: async () => {
      const data = audio.data;
      if (!data) throw new Error('Audio not loaded');
      const bid = promoteBatchId.trim();
      return promoteAudioTranscript(audioId, {
        target_project_id: data.project_id,
        research_batch_id: bid.length ? bid : null,
      });
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.sourceAudio(audioId) });
      setPromoteBatchId('');
    },
  });

  if (!audioId) return null;

  const transcriptId = audio.data?.transcript?.id;
  const transcriptionOnly = mode === 'transcription-only';
  const ts = audio.data?.transcript?.status;
  const pipelineBusy = shouldPollProgress(progress.data?.overall_status ?? undefined);
  const transcriptBusy = shouldPollTranscript(ts ?? undefined);
  const showWorkingBanner = pipelineBusy || transcriptBusy;

  return (
    <div className="space-y-6">
      {audio.isPending && <Skeleton className="h-32 w-full max-w-lg" />}
      {audio.error && <ApiErrorText error={audio.error} />}
      {audio.data && (
        <>
          <p className="text-sm text-muted-foreground">
            {transcriptionOnly ? ru.transcriptionPage.asrHint : ru.sourceAudio.transcribeOnlyNote}
          </p>

          <TranscriptionPipelinePanel
            progress={progress.data}
            progressLoading={progress.isFetching && !progress.data}
            transcriptStatus={ts}
            onRetry={() => transcribeMut.mutate()}
            retryPending={transcribeMut.isPending}
          />

          {progress.isError ? <ApiErrorText error={progress.error} /> : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="default" disabled={transcribeMut.isPending} onClick={() => transcribeMut.mutate()}>
              {transcribeMut.isPending ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" aria-hidden />
                  {ru.project.transcribeRunning}
                </>
              ) : (
                ru.sourceAudio.transcribe
              )}
            </Button>
            {transcriptId && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void downloadAudioTranscriptExport(
                      audioId,
                      'txt',
                      `${(audio.data?.filename || 'transcript').replace(/\.[^.]+$/, '')}_transcript.txt`,
                    )
                  }
                >
                  {ru.sourceAudio.downloadTxt}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void downloadAudioTranscriptExport(
                      audioId,
                      'docx',
                      `${(audio.data?.filename || 'transcript').replace(/\.[^.]+$/, '')}_transcript.docx`,
                    )
                  }
                >
                  {ru.sourceAudio.downloadDocx}
                </Button>
              </>
            )}
            {!transcriptionOnly && transcriptId && (
              <Button disabled={extractTxMut.isPending} onClick={() => extractTxMut.mutate(transcriptId)}>
                {extractTxMut.isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" aria-hidden />
                    {ru.project.insightsRunning}
                  </>
                ) : (
                  ru.sourceAudio.insightsFromT
                )}
              </Button>
            )}
          </div>

          {!transcriptionOnly && transcriptId && audio.data && (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="text-base">{ru.sourceAudio.promoteTitle}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">{ru.sourceAudio.promoteBatchHint}</p>
                <Input
                  value={promoteBatchId}
                  onChange={(e) => setPromoteBatchId(e.target.value)}
                  placeholder={ru.sourceAudio.promoteBatchPlaceholder}
                  className="font-mono text-xs"
                />
                <Button type="button" disabled={promoteMut.isPending} onClick={() => promoteMut.mutate()}>
                  {promoteMut.isPending ? (
                    <>
                      <Loader2 className="mr-2 size-4 animate-spin" aria-hidden />
                      {ru.sourceAudio.promoteRunning}
                    </>
                  ) : (
                    ru.sourceAudio.promoteSend
                  )}
                </Button>
                {promoteMut.error && <ApiErrorText error={promoteMut.error} />}
              </CardContent>
            </Card>
          )}

          {(() => {
            const err = transcribeMut.error || (!transcriptionOnly ? extractTxMut.error : undefined);
            return err ? <ApiErrorText error={err} /> : null;
          })()}

          {showWorkingBanner ? (
            <Alert>
              <AlertDescription className="flex items-center gap-2 text-sm">
                <Loader2 className="size-4 shrink-0 animate-spin text-primary" aria-hidden />
                {ru.pipeline.processingBanner}
              </AlertDescription>
            </Alert>
          ) : null}

          {audio.data.transcript && (
            <Card className="shadow-sm">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
                <CardTitle className="text-lg">{ru.sourceAudio.transcript}</CardTitle>
                <Badge variant={ts === 'completed' ? 'default' : ts === 'failed' ? 'destructive' : 'secondary'}>
                  {ts ? ru.pipeline.transcriptStatus(ts) : ru.transcriptionPage.statusNoTranscript}
                </Badge>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{audio.data.transcript.full_text}</p>
              </CardContent>
            </Card>
          )}

          {!transcriptionOnly && audio.data.transcript_segments_sample?.length ? (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg">{ru.sourceAudio.sample}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-4">
                  {audio.data.transcript_segments_sample.map((s) => (
                    <li key={s.id} className="border-b border-border/60 pb-4 last:border-0 last:pb-0">
                      <span className="text-xs text-muted-foreground">
                        {String(s.start_seconds)}с – {String(s.end_seconds)}с
                      </span>
                      <p className="mt-1 text-sm">{s.text}</p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}
