import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  getSourceDocument,
  queueChunkDocument,
  queueChunkDocumentSemantic,
  queueExtractDocument,
} from '../api/api';
import type { ProcessingTaskQueued } from '../api/types';
import { ApiErrorText } from '../components/ApiErrorText';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';

export function SourceDocumentPage() {
  const { documentId = '' } = useParams<{ documentId: string }>();
  const qc = useQueryClient();
  const [task, setTask] = useState<ProcessingTaskQueued | null>(null);
  const [poll, setPoll] = useState(false);

  useEffect(() => {
    if (!poll) return;
    const id = window.setTimeout(() => setPoll(false), 90_000);
    return () => window.clearTimeout(id);
  }, [poll]);

  const doc = useQuery({
    queryKey: qk.sourceDoc(documentId),
    queryFn: () => getSourceDocument(documentId),
    enabled: !!documentId,
    refetchInterval: poll ? 3000 : false,
  });

  const chunkMut = useMutation({
    mutationFn: () => queueChunkDocument(documentId),
    onSuccess: (t) => {
      setTask(t);
      setPoll(true);
      void qc.invalidateQueries({ queryKey: qk.sourceDoc(documentId) });
    },
  });

  const chunkSemanticMut = useMutation({
    mutationFn: () => queueChunkDocumentSemantic(documentId),
    onSuccess: (t) => {
      setTask(t);
      setPoll(true);
      void qc.invalidateQueries({ queryKey: qk.sourceDoc(documentId) });
    },
  });

  const extractMut = useMutation({
    mutationFn: () => queueExtractDocument(documentId),
    onSuccess: (t) => {
      setTask(t);
      setPoll(true);
      void qc.invalidateQueries({ queryKey: qk.sourceDoc(documentId) });
    },
  });

  if (!documentId) return <p className="text-sm text-muted-foreground">{ru.common.errorGeneric}</p>;

  return (
    <div className="space-y-8">
      <nav className="text-sm text-muted-foreground">
        <Link to="/projects" className="font-medium text-foreground hover:underline">
          {ru.nav.projects}
        </Link>
        <span className="mx-2">/</span>
        <span>{ru.sourceDoc.crumb}</span>
      </nav>

      {doc.isPending && <Skeleton className="h-32 w-full max-w-lg" />}
      {doc.error && <ApiErrorText error={doc.error} />}
      {doc.data && (
        <>
          <header className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">{doc.data.filename}</h1>
            <p className="font-mono text-xs text-muted-foreground">{doc.data.id}</p>
          </header>

          <Card className="shadow-sm">
            <CardContent className="grid gap-3 pt-6 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">{ru.sourceDoc.project}</span>
                <div className="mt-1">
                  <Link
                    to={`/projects/${doc.data.project_id}`}
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {ru.sourceDoc.openProject}
                  </Link>
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">{ru.sourceDoc.partsCount}</span>
                <div className="mt-1 font-medium">{doc.data.text_chunks_count}</div>
              </div>
              <div>
                <span className="text-muted-foreground">{ru.sourceDoc.insightsCount}</span>
                <div className="mt-1 font-medium">{doc.data.extracted_entities_count}</div>
              </div>
              <div>
                <span className="text-muted-foreground">{ru.sourceDoc.format}</span>
                <div className="mt-1 font-medium">{doc.data.mime_type ?? '—'}</div>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={chunkMut.isPending} onClick={() => chunkMut.mutate()}>
              {chunkMut.isPending ? ru.project.splitQueueing : ru.sourceDoc.split}
            </Button>
            <Button
              variant="outline"
              disabled={chunkSemanticMut.isPending}
              onClick={() => chunkSemanticMut.mutate()}
            >
              {chunkSemanticMut.isPending ? ru.project.splitQueueing : ru.sourceDoc.splitSemantic}
            </Button>
            <Button disabled={extractMut.isPending} onClick={() => extractMut.mutate()}>
              {extractMut.isPending ? ru.project.splitQueueing : ru.sourceDoc.insights}
            </Button>
          </div>
          {(chunkMut.error || chunkSemanticMut.error || extractMut.error) && (
            <ApiErrorText error={chunkMut.error || chunkSemanticMut.error || extractMut.error} />
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

          {doc.data.raw_text && (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg">{ru.sourceDoc.rawText}</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-4 text-sm">
                  {doc.data.raw_text}
                </pre>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
