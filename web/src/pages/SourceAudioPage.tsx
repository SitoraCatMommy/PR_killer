import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getSourceAudio, queueExtractTranscript, queueTranscribeAudio } from '../api/api';
import type { ProcessingTaskQueued } from '../api/types';
import { ApiErrorText } from '../components/ApiErrorText';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';

export function SourceAudioPage() {
  const { audioId = '' } = useParams<{ audioId: string }>();
  const qc = useQueryClient();
  const [task, setTask] = useState<ProcessingTaskQueued | null>(null);
  const [poll, setPoll] = useState(false);

  useEffect(() => {
    if (!poll) return;
    const id = window.setTimeout(() => setPoll(false), 90_000);
    return () => window.clearTimeout(id);
  }, [poll]);

  const audio = useQuery({
    queryKey: qk.sourceAudio(audioId),
    queryFn: () => getSourceAudio(audioId),
    enabled: !!audioId,
    refetchInterval: poll ? 3000 : false,
  });

  const transcribeMut = useMutation({
    mutationFn: () => queueTranscribeAudio(audioId),
    onSuccess: (t) => {
      setTask(t);
      setPoll(true);
      void qc.invalidateQueries({ queryKey: qk.sourceAudio(audioId) });
    },
  });

  const extractTxMut = useMutation({
    mutationFn: (transcriptId: string) => queueExtractTranscript(transcriptId),
    onSuccess: (t) => {
      setTask(t);
      setPoll(true);
      void qc.invalidateQueries({ queryKey: qk.sourceAudio(audioId) });
    },
  });

  if (!audioId) return <p className="text-sm text-muted-foreground">{ru.common.errorGeneric}</p>;

  const transcriptId = audio.data?.transcript?.id;

  return (
    <div className="space-y-8">
      <nav className="text-sm text-muted-foreground">
        <Link to="/projects" className="font-medium text-foreground hover:underline">
          {ru.nav.projects}
        </Link>
        <span className="mx-2">/</span>
        <span>{ru.sourceAudio.crumb}</span>
      </nav>

      {audio.isPending && <Skeleton className="h-32 w-full max-w-lg" />}
      {audio.error && <ApiErrorText error={audio.error} />}
      {audio.data && (
        <>
          <header className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">{audio.data.filename}</h1>
            <p className="font-mono text-xs text-muted-foreground">{audio.data.id}</p>
          </header>

          <Card className="shadow-sm">
            <CardContent className="grid gap-3 pt-6 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">{ru.sourceAudio.project}</span>
                <div className="mt-1">
                  <Link
                    to={`/projects/${audio.data.project_id}`}
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {ru.sourceAudio.openProject}
                  </Link>
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">{ru.sourceAudio.language}</span>
                <div className="mt-1 font-medium">{audio.data.language ?? '—'}</div>
              </div>
              <div>
                <span className="text-muted-foreground">{ru.sourceAudio.segments}</span>
                <div className="mt-1 font-medium">{audio.data.transcript_segments_count}</div>
              </div>
              <div>
                <span className="text-muted-foreground">{ru.sourceAudio.textParts}</span>
                <div className="mt-1 font-medium">{audio.data.text_chunks_count}</div>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={transcribeMut.isPending} onClick={() => transcribeMut.mutate()}>
              {transcribeMut.isPending ? ru.project.transcribeRunning : ru.sourceAudio.transcribe}
            </Button>
            {transcriptId && (
              <Button disabled={extractTxMut.isPending} onClick={() => extractTxMut.mutate(transcriptId)}>
                {extractTxMut.isPending ? ru.project.insightsRunning : ru.sourceAudio.insightsFromT}
              </Button>
            )}
          </div>
          {(transcribeMut.error || extractTxMut.error) && (
            <ApiErrorText error={transcribeMut.error || extractTxMut.error} />
          )}
          {poll && (
            <Alert>
              <AlertDescription>{ru.project.processingBanner}</AlertDescription>
            </Alert>
          )}
          {task && (
            <p className="text-xs text-muted-foreground">
              {ru.task.queued} · {ru.task.id}: <span className="font-mono">{task.task_id}</span>
            </p>
          )}

          {audio.data.transcript && (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg">
                  {ru.sourceAudio.transcript} ({audio.data.transcript.status})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{audio.data.transcript.full_text}</p>
              </CardContent>
            </Card>
          )}

          {audio.data.transcript_segments_sample?.length ? (
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
