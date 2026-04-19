import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getMaterial, reprocessMaterial } from '../api/api';
import { ApiErrorText } from '../components/ApiErrorText';
import type { MessageResponse } from '../api/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';

function statusRu(s: string): string {
  return ru.pipelineStatus[s] ?? s;
}

export function MaterialDetailPage() {
  const { materialId = '' } = useParams<{ materialId: string }>();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<MessageResponse | null>(null);

  const material = useQuery({
    queryKey: qk.material(materialId),
    queryFn: () => getMaterial(materialId),
    enabled: !!materialId,
  });

  const reprocess = useMutation({
    mutationFn: () => reprocessMaterial(materialId),
    onSuccess: (m) => {
      setMsg(m);
      void qc.invalidateQueries({ queryKey: qk.material(materialId) });
    },
  });

  if (!materialId) return <p className="text-sm text-muted-foreground">{ru.common.errorGeneric}</p>;

  return (
    <div className="space-y-8">
      <nav className="text-sm text-muted-foreground">
        <Link to="/materials" className="font-medium text-foreground hover:underline">
          {ru.nav.materials}
        </Link>
        <span className="mx-2">/</span>
        <span>{ru.materialDetail.crumb}</span>
      </nav>

      {material.isPending && <Skeleton className="h-32 w-full max-w-lg" />}
      {material.error && <ApiErrorText error={material.error} />}
      {material.data && (
        <>
          <header className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              {material.data.title ?? ru.materials.title}
            </h1>
            <p className="font-mono text-xs text-muted-foreground">{material.data.id}</p>
          </header>

          <Card className="shadow-sm">
            <CardContent className="grid gap-3 pt-6 text-sm">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-muted-foreground">{ru.materialDetail.type}</span>
                <span className="font-medium">
                  {material.data.material_type === 'audio' ? ru.materials.typeAudio : ru.materials.typeText}
                </span>
              </div>
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-muted-foreground">{ru.materialDetail.status}</span>
                <span className="font-medium">{statusRu(material.data.status)}</span>
              </div>
              {material.data.processing_error && (
                <div className="flex flex-col gap-1">
                  <span className="text-muted-foreground">{ru.materialDetail.error}</span>
                  <span className="text-destructive">{material.data.processing_error}</span>
                </div>
              )}
            </CardContent>
          </Card>

          <Button disabled={reprocess.isPending} onClick={() => reprocess.mutate()}>
            {reprocess.isPending ? ru.materialDetail.reprocessQueueing : ru.materialDetail.reprocess}
          </Button>
          {reprocess.error && <ApiErrorText error={reprocess.error} />}
          {msg && <p className="text-sm text-muted-foreground">{msg.message}</p>}

          {material.data.raw_text && (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle className="text-lg">{ru.materialDetail.rawText}</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-4 text-sm">
                  {material.data.raw_text}
                </pre>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
