import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ingestMaterialAudio, ingestMaterialText, listMaterials } from '../api/api';
import { ApiErrorText } from '../components/ApiErrorText';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';

const LIMIT = 50;

function statusRu(s: string): string {
  return ru.pipelineStatus[s] ?? s;
}

export function MaterialsPage() {
  const [title, setTitle] = useState('');
  const [rawText, setRawText] = useState('');
  const qc = useQueryClient();

  const list = useQuery({
    queryKey: qk.materials(LIMIT),
    queryFn: () => listMaterials(LIMIT),
  });

  const textMut = useMutation({
    mutationFn: () =>
      ingestMaterialText({
        material_type: 'text',
        raw_text: rawText,
        title: title.trim() || null,
        source_uri: null,
        mime_type: 'text/plain',
        extra_metadata: {},
      }),
    onSuccess: () => {
      setRawText('');
      setTitle('');
      void qc.invalidateQueries({ queryKey: ['materials'] });
    },
  });

  const audioMut = useMutation({
    mutationFn: (file: File) => ingestMaterialAudio(file, { title: title.trim() || undefined }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['materials'] });
    },
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{ru.materials.title}</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">{ru.materials.lede}</p>
      </div>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{ru.materials.ingestText}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid max-w-xl gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (rawText.trim()) textMut.mutate();
            }}
          >
            <div className="space-y-2">
              <span className="text-sm font-medium">{ru.materials.titleField}</span>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={ru.common.optional}
              />
            </div>
            <div className="space-y-2">
              <span className="text-sm font-medium">{ru.materials.textField}</span>
              <Textarea value={rawText} onChange={(e) => setRawText(e.target.value)} rows={6} required />
            </div>
            <Button type="submit" disabled={textMut.isPending}>
              {textMut.isPending ? ru.materials.sending : ru.materials.send}
            </Button>
            {textMut.error && <ApiErrorText error={textMut.error} />}
          </form>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{ru.materials.ingestAudio}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className={cn(buttonVariants({ variant: 'outline' }), 'cursor-pointer')}>
            {ru.materials.chooseAudio}
            <input
              type="file"
              className="sr-only"
              accept="audio/*"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) audioMut.mutate(f);
                e.target.value = '';
              }}
            />
          </label>
          {audioMut.error && <ApiErrorText error={audioMut.error} />}
          {audioMut.isSuccess && (
            <p className="text-sm text-muted-foreground">{ru.materials.uploaded}</p>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{ru.materials.recent}</CardTitle>
        </CardHeader>
        <CardContent>
          {list.isPending && <Skeleton className="h-32 w-full" />}
          {list.error && <ApiErrorText error={list.error} />}
          {list.data && (
            <ul className="divide-y rounded-lg border">
              {list.data.map((m) => (
                <li key={m.id}>
                  <Link
                    to={`/materials/${m.id}`}
                    className={cn(
                      buttonVariants({ variant: 'ghost' }),
                      'h-auto w-full flex-col items-start gap-1 rounded-none px-4 py-3 hover:bg-muted/60',
                    )}
                  >
                    <span className="font-medium">{m.title ?? m.id}</span>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">
                        {m.material_type === 'audio' ? ru.materials.typeAudio : ru.materials.typeText}
                      </Badge>
                      <Badge variant="outline">{statusRu(m.status)}</Badge>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
