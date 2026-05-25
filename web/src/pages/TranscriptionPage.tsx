import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createProject,
  getSourceAudio,
  listProjects,
  queueTranscribeAudio,
  uploadAudioSource,
} from '../api/api';
import type { TranscriptionLanguageOption } from '../api/types';
import { ApiErrorText } from '../components/ApiErrorText';
import { AudioTranscriptionWorkflow } from '../components/AudioTranscriptionWorkflow';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';
import { Check } from 'lucide-react';

const TX_SINK_STORAGE_KEY = 'ri_transcription_sink_project_v1';
const TX_SINK_PROJECT_NAME = 'Транскрибация — загрузки';

/** Контур «Транскрибация»: одно аудио → текст → TXT/DOCX. Проект выбирается автоматически (служебная запись). */
export function TranscriptionPage() {
  const qc = useQueryClient();
  const [sinkProjectId, setSinkProjectId] = useState(() => localStorage.getItem(TX_SINK_STORAGE_KEY) ?? '');
  const [transcriptionLang, setTranscriptionLang] = useState<TranscriptionLanguageOption>('auto');
  const [uploadedAudioId, setUploadedAudioId] = useState<string | null>(null);
  const sinkEnsureStarted = useRef(false);

  const projects = useQuery({
    queryKey: qk.projects(0, 100),
    queryFn: () => listProjects(0, 100),
  });

  const createSinkMut = useMutation({
    mutationFn: () =>
      createProject({
        name: TX_SINK_PROJECT_NAME,
        description: 'Служебный проект для загрузок из раздела «Транскрибация».',
      }),
    onSuccess: (p) => {
      localStorage.setItem(TX_SINK_STORAGE_KEY, p.id);
      setSinkProjectId(p.id);
      void qc.invalidateQueries({ queryKey: qk.projects(0, 100) });
    },
  });

  useEffect(() => {
    if (!projects.isSuccess || !projects.data?.items?.length || sinkProjectId) return;
    const stored = localStorage.getItem(TX_SINK_STORAGE_KEY);
    if (stored && projects.data.items.some((p) => p.id === stored)) {
      setSinkProjectId(stored);
      return;
    }
    const found = projects.data.items.find((p) => p.name === TX_SINK_PROJECT_NAME);
    if (found) {
      localStorage.setItem(TX_SINK_STORAGE_KEY, found.id);
      setSinkProjectId(found.id);
      return;
    }
    if (sinkEnsureStarted.current || createSinkMut.isPending) return;
    sinkEnsureStarted.current = true;
    createSinkMut.mutate(undefined, {
      onError: () => {
        sinkEnsureStarted.current = false;
      },
    });
  }, [projects.isSuccess, projects.data, sinkProjectId, createSinkMut]);

  const uploadedPeek = useQuery({
    queryKey: uploadedAudioId ? qk.sourceAudio(uploadedAudioId) : ['sourceAudio', 'none'],
    queryFn: () => getSourceAudio(uploadedAudioId!),
    enabled: !!uploadedAudioId,
    refetchInterval: (q) => {
      const st = q.state.data?.transcript?.status?.toLowerCase();
      if (!st || st === 'completed' || st === 'failed' || st === 'cancelled') return false;
      return 3000;
    },
  });

  const transcriptDone = uploadedPeek.data?.transcript?.status === 'completed';

  const uploadMut = useMutation({
    mutationFn: (file: File) =>
      uploadAudioSource(sinkProjectId, file, {
        language: transcriptionLang === 'auto' ? undefined : transcriptionLang,
        sourceType: 'upload',
      }),
    onSuccess: async (row) => {
      setUploadedAudioId(row.id);
      void qc.invalidateQueries({ queryKey: ['sources', sinkProjectId] });
      void qc.invalidateQueries({ queryKey: ['projects'] });
      try {
        await queueTranscribeAudio(row.id);
        await qc.invalidateQueries({ queryKey: qk.sourceAudio(row.id) });
        await qc.invalidateQueries({ queryKey: qk.sourceAudioProgress(row.id) });
      } catch {
        /* пользователь запустит расшифровку кнопкой на следующем экране */
      }
    },
  });

  const sinkReady = !!sinkProjectId;
  const sinkBusy = projects.isPending || (!sinkReady && (createSinkMut.isPending || projects.isSuccess));

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <nav className="text-sm text-muted-foreground">
        <Link to="/" className="font-medium text-foreground hover:underline">
          {ru.nav.home}
        </Link>
        <span className="mx-2">/</span>
        <span>{ru.transcriptionPage.crumb}</span>
      </nav>

      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{ru.transcriptionPage.title}</h1>
        <p className="text-sm text-muted-foreground">{ru.transcriptionPage.lede}</p>
        <p className="text-xs text-muted-foreground">{ru.transcriptionPage.sinkNote}</p>
      </header>

      <ol className="grid gap-3 sm:grid-cols-3">
        {(
          [
            { step: 1, label: ru.transcriptionPage.flowStep1 },
            { step: 2, label: ru.transcriptionPage.flowStep2 },
            { step: 3, label: ru.transcriptionPage.flowStep3 },
          ] as const
        ).map(({ step, label }) => {
          const done =
            (step === 1 && !!uploadedAudioId) ||
            (step === 2 && transcriptDone) ||
            (step === 3 && transcriptDone);
          const active = step === 2 && !!uploadedAudioId && !transcriptDone;
          return (
            <li
              key={step}
              className={cn(
                'flex items-start gap-3 rounded-lg border p-3 text-sm',
                done && 'border-primary/30 bg-primary/5',
                active && 'ring-1 ring-primary/20',
              )}
            >
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold',
                  done ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/30',
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : step}
              </span>
              <span className="leading-snug text-muted-foreground">{label}</span>
            </li>
          );
        })}
      </ol>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>{ru.transcriptionPage.cardTitle}</CardTitle>
          <CardDescription>{ru.transcriptionPage.cardDescription}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {sinkBusy && !sinkReady && <Skeleton className="h-10 w-full" />}
          {createSinkMut.error && <ApiErrorText error={createSinkMut.error} />}
          {projects.error && <ApiErrorText error={projects.error} />}
          {sinkReady && (
            <>
              <div className="flex max-w-lg flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                <span className="text-sm font-medium shrink-0">{ru.transcriptionPage.interviewLanguageLabel}</span>
                <Select
                  value={transcriptionLang}
                  onValueChange={(v) => setTranscriptionLang(v as TranscriptionLanguageOption)}
                >
                  <SelectTrigger className="w-full sm:w-[220px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{ru.project.audioLangAuto}</SelectItem>
                    <SelectItem value="ru">{ru.project.audioLangRu}</SelectItem>
                    <SelectItem value="uz">{ru.project.audioLangUz}</SelectItem>
                    <SelectItem value="en">{ru.project.audioLangEn}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label
                  className={cn(buttonVariants({ variant: 'default' }), 'inline-flex cursor-pointer')}
                >
                  {ru.transcriptionPage.chooseFile}
                  <input
                    type="file"
                    className="sr-only"
                    accept="audio/*"
                    disabled={uploadMut.isPending}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadMut.mutate(f);
                      e.target.value = '';
                    }}
                  />
                </label>
              </div>
              {uploadMut.error && <ApiErrorText error={uploadMut.error} />}
              {uploadMut.isSuccess && uploadedAudioId && (
                <p className="text-sm text-muted-foreground">
                  {ru.transcriptionPage.uploadOk} {ru.transcriptionPage.autoStartNote}
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {uploadedAudioId && (
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 space-y-0">
            <div>
              <CardTitle className="text-lg">{ru.transcriptionPage.resultTitle}</CardTitle>
              <CardDescription>{ru.transcriptionPage.resultDescription}</CardDescription>
            </div>
            <Link
              to={`/sources/audios/${uploadedAudioId}`}
              className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'shrink-0')}
            >
              {ru.transcriptionPage.openDetailPage}
            </Link>
          </CardHeader>
          <CardContent>
            <AudioTranscriptionWorkflow audioId={uploadedAudioId} mode="transcription-only" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
