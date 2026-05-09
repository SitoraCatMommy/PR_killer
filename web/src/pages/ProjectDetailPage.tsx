import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import {
  createRawTextNote,
  deleteProject,
  getPRAnalysisReadiness,
  getProject,
  getProjectAggregation,
  getProjectReport,
  getProjectSummary,
  getSourceAudio,
  getSourceDocument,
  listDocumentChunks,
  listProjectEntities,
  listProjectSources,
  queueExtractDocument,
  queueExtractTranscript,
  queueGenerateProjectSummary,
  queueGenerateResearchReport,
  queueRegenerateResearchReport,
  queueProjectAggregate,
  queueTranscribeAudio,
  uploadAudioSource,
  uploadTextSource,
} from '../api/api';
import type {
  EntityListResponse,
  EntityType,
  PRAnalysisReadiness,
  ResearchReportRead,
  ResearchSummaryRead,
  SourceAudioDetailRead,
  SourceDocumentDetailRead,
  SourceType,
} from '../api/types';
import { ApiErrorText } from '../components/ApiErrorText';
import { ResearchReportView } from '../components/ResearchReportView';
import { ProgressSteps } from '../components/ProgressSteps';
import { SummaryOutcome } from '../components/SummaryOutcome';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { ENTITY_TYPE_RU, SOURCE_TYPE_RU, formatConfidence, ru } from '../i18n/ru';
import { isTrivialQuote } from '../utils/quoteFilters';
import { qk } from '../queryKeys';
import { ChevronDown, Loader2, RefreshCw } from 'lucide-react';

/** PR-facing synthesis types only (no «подтверждающий факт», no generic product rec/opportunity in filter). */
const PRIMARY_RESEARCH_FILTER_TYPES: EntityType[] = [
  'problem',
  'pain_point',
  'user_need',
  'behavior_pattern',
  'trust_issue',
  'adoption_barrier',
  'risk',
  'hypothesis',
  'open_question',
  'sentiment_signal',
];

const PAGE = 25;
const POLL_MS = 3000;
const POLL_MAX_MS = 120_000;
const FOCUS_NONE = '__none__';

type SourceKind = 'document' | 'audio';

function readinessBlockText(code: string): string {
  const map = ru.project as unknown as Record<string, string>;
  return map[`readinessBlock_${code}`] ?? code;
}

function readinessWarnText(code: string): string {
  const map = ru.project as unknown as Record<string, string>;
  return map[`readinessWarn_${code}`] ?? code;
}

function reportStageText(report: ResearchReportRead | null | undefined): string {
  const extras = report?.report_extras_json;
  const stage = extras?.stage;
  if (stage === 'preparing') return ru.project.reportStagePreparing;
  if (stage === 'generating_report') return ru.project.reportStageGenerating;
  return ru.project.reportStatusGenerating;
}

function reportFailureText(report: ResearchReportRead | null | undefined): string {
  const extras = report?.report_extras_json;
  if (extras?.error_message) return extras.error_message;
  if (extras?.error_code) return readinessBlockText(extras.error_code);
  return ru.project.reportStatusFailed;
}

function PRReadinessCard({
  readiness,
  isPending,
  error,
}: {
  readiness: PRAnalysisReadiness | undefined;
  isPending: boolean;
  error: unknown;
}) {
  if (isPending) {
    return (
      <Card className="border-dashed bg-muted/10 shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">{ru.project.readinessTitle}</CardTitle>
          <CardDescription>{ru.project.readinessIntro}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    );
  }
  if (error) return <ApiErrorText error={error} />;
  if (!readiness) return null;
  const stat = [
    [ru.project.readinessSources, readiness.source_count],
    [ru.project.readinessChunks, readiness.chunk_count],
    [ru.project.readinessEntities, readiness.entity_count],
    [
      `${ru.project.readinessPrSignals} (${ru.project.readinessMinSignals} ${readiness.min_pr_entity_count})`,
      readiness.pr_entity_count,
    ],
  ] as const;
  return (
    <Card className={cn('shadow-sm', readiness.ready_for_report ? 'border-emerald-500/30' : 'border-amber-500/30')}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{ru.project.readinessTitle}</CardTitle>
          <Badge variant={readiness.ready_for_report ? 'secondary' : 'outline'}>
            {readiness.ready_for_report ? ru.project.readinessReady : ru.project.readinessBlocked}
          </Badge>
        </div>
        <CardDescription>{ru.project.readinessIntro}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {stat.map(([label, value]) => (
            <div key={label} className="rounded-md border bg-background p-3">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-lg font-semibold">{value}</p>
            </div>
          ))}
          <div className="rounded-md border bg-background p-3">
            <p className="text-xs text-muted-foreground">{ru.project.readinessAggregation}</p>
            <p className="text-sm font-medium">
              {readiness.aggregation_exists
                ? ru.project.readinessAggregationReady
                : ru.project.readinessAggregationMissing}
            </p>
          </div>
        </div>
        {!!readiness.blocking_reasons.length && (
          <div className="space-y-1 text-sm">
            {readiness.blocking_reasons.map((code) => (
              <p key={code} className="text-amber-700 dark:text-amber-300">
                • {readinessBlockText(code)}
              </p>
            ))}
          </div>
        )}
        {!!readiness.warnings.length && (
          <div className="space-y-1 text-xs text-muted-foreground">
            {readiness.warnings.map((code) => (
              <p key={code}>• {readinessWarnText(code)}</p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

type PollState =
  | { t: 'chunks'; docId: string; n: number }
  | { t: 'ent'; docId: string; n: number }
  | { t: 'aud'; audioId: string; transcriptStatus: string | null }
  | { t: 'audio_chunks'; audioId: string; n: number }
  | { t: 'txent'; total: number }
  | { t: 'agg'; created: string | null }
  | { t: 'sum'; key: string };

/** True while Celery job may still be running (max duration handled by a separate timeout effect). */
function shouldKeepPolling(
  poll: PollState | null,
  ctx: {
    focus: { kind: SourceKind; id: string } | null;
    d: SourceDocumentDetailRead | undefined;
    a: SourceAudioDetailRead | undefined;
    entTotal: number;
    aggCreated: string | null;
    summary: ResearchSummaryRead | null | undefined;
  },
): boolean {
  if (!poll) return false;
  if (poll.t === 'chunks' && ctx.focus?.kind === 'document' && ctx.focus.id === poll.docId) {
    if ((ctx.d?.text_chunks_count ?? 0) > poll.n) return false;
    return true;
  }
  if (poll.t === 'ent' && ctx.focus?.kind === 'document' && ctx.focus.id === poll.docId) {
    if ((ctx.d?.extracted_entities_count ?? 0) > poll.n) return false;
    return true;
  }
  if (poll.t === 'aud' && ctx.focus?.kind === 'audio' && ctx.focus.id === poll.audioId) {
    const st = ctx.a?.transcript?.status ?? null;
    if (st === 'completed' && poll.transcriptStatus !== 'completed') return false;
    if (st === 'failed') return false;
    return true;
  }
  if (poll.t === 'audio_chunks' && ctx.focus?.kind === 'audio' && ctx.focus.id === poll.audioId) {
    if ((ctx.a?.text_chunks_count ?? 0) > poll.n) return false;
    return true;
  }
  if (poll.t === 'txent') {
    if (ctx.entTotal > poll.total) return false;
    return true;
  }
  if (poll.t === 'agg') {
    const ca = ctx.aggCreated;
    if (ca && ca !== poll.created) return false;
    return true;
  }
  if (poll.t === 'sum') {
    if (summaryKey(ctx.summary ?? undefined) !== poll.key) return false;
    return true;
  }
  return false;
}

function evidenceQuoteFromJson(
  ev: Record<string, unknown> | unknown[] | null | undefined,
): string | null {
  if (ev && typeof ev === 'object' && !Array.isArray(ev)) {
    const q = (ev as Record<string, unknown>).quote;
    if (typeof q === 'string' && q.trim()) {
      const t = q.trim();
      if (isTrivialQuote(t)) return null;
      return t;
    }
  }
  return null;
}

function clipText(s: string, max: number) {
  const t = s.trim();
  if (!t) return '';
  return t.length <= max ? t : `${t.slice(0, max - 1)}…`;
}

type Phase = 'todo' | 'doing' | 'done';

function docPhases(d: SourceDocumentDetailRead | undefined): { parts: Phase; insights: Phase } {
  if (!d) return { parts: 'todo', insights: 'todo' };
  const parts: Phase = d.text_chunks_count > 0 ? 'done' : 'todo';
  const insights: Phase = d.extracted_entities_count > 0 ? 'done' : 'todo';
  return { parts, insights };
}

function audioPhases(
  a: SourceAudioDetailRead | undefined,
): { transcript: Phase; parts: Phase; insights: Phase } {
  if (!a) return { transcript: 'todo', parts: 'todo', insights: 'todo' };
  let transcript: Phase = 'todo';
  if (a.transcript) {
    const st = a.transcript.status;
    if (st === 'completed') transcript = 'done';
    else if (st === 'failed' || st === 'cancelled') transcript = 'todo';
    else if (st === 'queued' || st === 'running' || st === 'pending') transcript = 'doing';
  }
  const parts: Phase = (a.text_chunks_count ?? 0) > 0 ? 'done' : 'todo';
  const insights: Phase = (a.extracted_entities_count ?? 0) > 0 ? 'done' : 'todo';
  return { transcript, parts, insights };
}

function phaseLabel(p: Phase): string {
  if (p === 'done') return ru.project.statusDone;
  if (p === 'doing') return ru.project.statusInProgress;
  return ru.project.statusNotStarted;
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

function summaryKey(s: ResearchSummaryRead | null | undefined): string {
  if (!s) return 'null';
  return `${s.id}:${s.status}:${s.summary_text?.length ?? 0}`;
}

function pollBannerText(poll: PollState): string {
  switch (poll.t) {
    case 'chunks':
    case 'audio_chunks':
      return ru.project.bannerPreparingMaterial;
    case 'ent':
    case 'txent':
      return ru.project.bannerExtractingInsights;
    case 'aud':
      return ru.project.bannerTranscribing;
    case 'agg':
      return ru.project.bannerAggregating;
    case 'sum':
      return ru.project.bannerSummary;
    default:
      return ru.project.processingBannerFallback;
  }
}

export function ProjectDetailPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [srcOffset, setSrcOffset] = useState(0);
  const [entOffset, setEntOffset] = useState(0);
  const [entityType, setEntityType] = useState<EntityType | ''>('');
  const [minConfidence, setMinConfidence] = useState('');
  const [showAllEntityTypes, setShowAllEntityTypes] = useState(false);

  const [rawTitle, setRawTitle] = useState('');
  const [rawText, setRawText] = useState('');
  const [uploadSourceType, setUploadSourceType] = useState<SourceType>('upload');

  const [focusKey, setFocusKey] = useState('');
  const [workspaceTab, setWorkspaceTab] = useState('report');
  const [reportPolling, setReportPolling] = useState(false);
  const [poll, setPoll] = useState<PollState | null>(null);
  const [expandedChunks, setExpandedChunks] = useState<Record<string, boolean>>({});

  const entityQueryKey = useMemo(
    () =>
      JSON.stringify({
        entityType: entityType || undefined,
        minConfidence: minConfidence || undefined,
        entOffset,
        showAllEntityTypes,
      }),
    [entityType, minConfidence, entOffset, showAllEntityTypes],
  );

  const refetchInterval = poll ? POLL_MS : false;

  const project = useQuery({
    queryKey: qk.project(projectId),
    queryFn: () => getProject(projectId),
    enabled: !!projectId,
  });

  const sources = useQuery({
    queryKey: qk.sources(projectId, srcOffset, PAGE),
    queryFn: () => listProjectSources(projectId, srcOffset, PAGE),
    enabled: !!projectId,
    refetchInterval,
  });

  const entities = useQuery({
    queryKey: qk.entities(projectId, entityQueryKey),
    queryFn: () =>
      listProjectEntities(projectId, {
        offset: entOffset,
        limit: PAGE,
        entity_type: entityType || undefined,
        min_confidence: minConfidence ? Number(minConfidence) : undefined,
        include_all_types: showAllEntityTypes || undefined,
      }),
    enabled: !!projectId,
    refetchInterval,
  });

  const summary = useQuery({
    queryKey: qk.summary(projectId),
    queryFn: async () => {
      try {
        return await getProjectSummary(projectId);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    enabled: !!projectId,
    refetchInterval,
  });

  const projectReport = useQuery({
    queryKey: qk.projectReport(projectId),
    queryFn: () => getProjectReport(projectId),
    enabled: !!projectId,
    refetchInterval: reportPolling ? POLL_MS : false,
  });

  const readiness = useQuery({
    queryKey: qk.prAnalysisReadiness(projectId),
    queryFn: () => getPRAnalysisReadiness(projectId),
    enabled: !!projectId,
    refetchInterval: reportPolling || poll != null ? POLL_MS : false,
  });

  const aggregation = useQuery({
    queryKey: qk.projectAggregation(projectId),
    queryFn: () => getProjectAggregation(projectId),
    enabled: !!projectId,
    refetchInterval,
  });

  const focus = useMemo(() => {
    if (!focusKey) return null;
    const [kind, id] = focusKey.split(':') as [string, string];
    if ((kind === 'document' || kind === 'audio') && id) return { kind, id } as { kind: SourceKind; id: string };
    return null;
  }, [focusKey]);

  const detailDoc = useQuery({
    queryKey: qk.sourceDoc(focus?.kind === 'document' ? focus.id : ''),
    queryFn: () => getSourceDocument(focus!.id),
    enabled: !!projectId && focus?.kind === 'document',
    refetchInterval,
  });

  const detailAudio = useQuery({
    queryKey: qk.sourceAudio(focus?.kind === 'audio' ? focus.id : ''),
    queryFn: () => getSourceAudio(focus!.id),
    enabled: !!projectId && focus?.kind === 'audio',
    refetchInterval,
  });

  const d = detailDoc.data;
  const a = detailAudio.data;

  const documentChunks = useQuery({
    queryKey: qk.documentChunks(focus?.kind === 'document' ? focus.id : ''),
    queryFn: () => listDocumentChunks(focus!.id),
    enabled:
      !!projectId &&
      focus?.kind === 'document' &&
      ((d?.text_chunks_count ?? 0) > 0 ||
        (poll?.t === 'ent' && focus?.kind === 'document' && poll.docId === focus.id)),
    refetchInterval:
      (poll?.t === 'chunks' || poll?.t === 'ent') &&
      focus?.kind === 'document' &&
      poll.docId === focus?.id
        ? POLL_MS
        : false,
  });

  useEffect(() => {
    if (!poll) return;
    const t = window.setTimeout(() => setPoll(null), POLL_MAX_MS);
    return () => window.clearTimeout(t);
  }, [poll]);

  const entMeta = entities.data?.meta;
  const prReady: PRAnalysisReadiness | undefined = readiness.data;

  useEffect(() => {
    if (!poll) return;
    if (
      !shouldKeepPolling(poll, {
        focus,
        d,
        a,
        entTotal: entMeta?.total ?? 0,
        aggCreated: aggregation.data?.snapshot?.created_at ?? null,
        summary: summary.data,
      })
    ) {
      queueMicrotask(() => setPoll(null));
    }
  }, [poll, focus, d, a, entMeta?.total, aggregation.data?.snapshot?.created_at, summary.data]);

  const invalidateSources = () => void qc.invalidateQueries({ queryKey: ['sources', projectId] });
  const invalidateReadiness = () =>
    void qc.invalidateQueries({ queryKey: qk.prAnalysisReadiness(projectId) });

  const invalidateAll = () => {
    invalidateSources();
    invalidateReadiness();
    void qc.invalidateQueries({ queryKey: qk.summary(projectId) });
    void qc.invalidateQueries({ queryKey: qk.projectReport(projectId) });
    void qc.invalidateQueries({ queryKey: ['entities', projectId] });
    void qc.invalidateQueries({ queryKey: qk.projectAggregation(projectId) });
    if (focus?.kind === 'document') void qc.invalidateQueries({ queryKey: qk.sourceDoc(focus.id) });
    if (focus?.kind === 'audio') void qc.invalidateQueries({ queryKey: qk.sourceAudio(focus.id) });
    if (focus?.kind === 'document')
      void qc.invalidateQueries({ queryKey: qk.documentChunks(focus.id) });
  };

  const uploadTextMut = useMutation({
    mutationFn: (file: File) => uploadTextSource(projectId, file, uploadSourceType),
    onSuccess: () => {
      invalidateSources();
      invalidateReadiness();
    },
  });

  const uploadAudioMut = useMutation({
    mutationFn: ({ file, language }: { file: File; language?: string }) =>
      uploadAudioSource(projectId, file, { language: language || undefined, sourceType: uploadSourceType }),
    onSuccess: () => {
      invalidateSources();
      invalidateReadiness();
    },
  });

  const rawNoteMut = useMutation({
    mutationFn: () =>
      createRawTextNote(projectId, {
        title: rawTitle.trim(),
        text: rawText,
        metadata_json: null,
      }),
    onSuccess: () => {
      setRawTitle('');
      setRawText('');
      invalidateSources();
      invalidateReadiness();
    },
  });

  const extractDocMut = useMutation({
    mutationFn: () => queueExtractDocument(focus!.id),
    onSuccess: () => {
      const id = focus!.id;
      const cur = qc.getQueryData(qk.sourceDoc(id)) as SourceDocumentDetailRead | undefined;
      setPoll({ t: 'ent', docId: id, n: cur?.extracted_entities_count ?? 0 });
      invalidateAll();
    },
  });

  const transcribeMut = useMutation({
    mutationFn: () => queueTranscribeAudio(focus!.id),
    onSuccess: () => {
      const id = focus!.id;
      const cur = qc.getQueryData(qk.sourceAudio(id)) as SourceAudioDetailRead | undefined;
      setPoll({
        t: 'aud',
        audioId: id,
        transcriptStatus: cur?.transcript?.status ?? null,
      });
      invalidateAll();
    },
  });

  const extractTxMut = useMutation({
    mutationFn: (tid: string) => queueExtractTranscript(tid),
    onSuccess: () => {
      const ents = qc.getQueryData(qk.entities(projectId, entityQueryKey)) as EntityListResponse | undefined;
      setPoll({ t: 'txent', total: ents?.meta.total ?? 0 });
      invalidateAll();
    },
  });

  const aggregateMut = useMutation({
    mutationFn: () => queueProjectAggregate(projectId),
    onSuccess: () => {
      const ag = qc.getQueryData(qk.projectAggregation(projectId)) as
        | { snapshot: { created_at: string } | null }
        | undefined;
      setPoll({ t: 'agg', created: ag?.snapshot?.created_at ?? null });
      void qc.invalidateQueries({ queryKey: qk.projectAggregation(projectId) });
    },
  });

  const genSummaryMut = useMutation({
    mutationFn: () => queueGenerateProjectSummary(projectId),
    onSuccess: () => {
      const s = qc.getQueryData(qk.summary(projectId)) as ResearchSummaryRead | null | undefined;
      setPoll({ t: 'sum', key: summaryKey(s) });
      void qc.invalidateQueries({ queryKey: qk.summary(projectId) });
    },
  });

  const reportGenMut = useMutation({
    mutationFn: () => queueGenerateResearchReport(projectId),
    onMutate: () => setReportPolling(true),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.projectReport(projectId) });
      invalidateReadiness();
      void qc.invalidateQueries({ queryKey: ['entities', projectId] });
      void qc.invalidateQueries({ queryKey: qk.projectAggregation(projectId) });
      setWorkspaceTab('report');
    },
    onError: () => setReportPolling(false),
  });

  const reportRegenMut = useMutation({
    mutationFn: () => queueRegenerateResearchReport(projectId),
    onMutate: () => setReportPolling(true),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.projectReport(projectId) });
      invalidateReadiness();
      void qc.invalidateQueries({ queryKey: ['entities', projectId] });
      void qc.invalidateQueries({ queryKey: qk.projectAggregation(projectId) });
      setWorkspaceTab('report');
    },
    onError: () => setReportPolling(false),
  });

  const deleteProjectMut = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      void navigate('/projects');
    },
  });

  useEffect(() => {
    if (!reportPolling) return;
    const st = projectReport.data?.report?.status;
    if (st === 'ready' || st === 'failed') queueMicrotask(() => setReportPolling(false));
  }, [reportPolling, projectReport.data?.report?.status]);

  const srcMeta = sources.data?.meta;
  const hasData = (prReady?.source_count ?? srcMeta?.total ?? 0) > 0;
  const hasInsights = (entMeta?.total ?? 0) > 0;
  const hasReport = projectReport.data?.report?.status === 'ready';
  const hasSummary = summary.data != null;

  const touchedProcessing =
    (prReady?.chunk_count ?? 0) > 0 ||
    (prReady?.entity_count ?? 0) > 0 ||
    hasInsights ||
    (d?.text_chunks_count ?? 0) > 0 ||
    (d?.extracted_entities_count ?? 0) > 0 ||
    !!a?.transcript ||
    (a?.transcript_segments_count ?? 0) > 0 ||
    (a?.text_chunks_count ?? 0) > 0 ||
    (a?.extracted_entities_count ?? 0) > 0;

  const docP = docPhases(d);
  const audP = audioPhases(a);

  const processingBanner =
    poll &&
    shouldKeepPolling(poll, {
      focus,
      d,
      a,
      entTotal: entMeta?.total ?? 0,
      aggCreated: aggregation.data?.snapshot?.created_at ?? null,
      summary: summary.data,
    });
  const readinessBlockers = prReady?.blocking_reasons ?? [];
  const reportHardBlocked =
    readinessBlockers.includes('no_processable_sources') ||
    (readinessBlockers.includes('low_pr_signal') &&
      (prReady?.needs_chunking_count ?? 0) === 0 &&
      (prReady?.needs_extraction_count ?? 0) === 0);

  function sourceStatusForRow(item: { source_kind: string; id: string }) {
    if (focus?.kind === 'document' && item.source_kind === 'document' && item.id === focus.id && d) {
      return `${ru.project.partsCountShort(d.text_chunks_count)} · ${ru.project.insightsCountShort(d.extracted_entities_count)}`;
    }
    if (focus?.kind === 'audio' && item.source_kind === 'audio' && item.id === focus.id && a) {
      return `${ru.project.partsCountShort(a.text_chunks_count)} · ${ru.project.insightsCountShort(a.extracted_entities_count)}`;
    }
    return '—';
  }

  if (!projectId) {
    return <p className="text-sm text-muted-foreground">{ru.common.errorGeneric}</p>;
  }

  return (
    <div className="space-y-8">
      <nav className="text-sm text-muted-foreground">
        <Link to="/projects" className="font-medium text-foreground hover:underline">
          {ru.nav.projects}
        </Link>
        <span className="mx-2">/</span>
        <span>{ru.project.crumb}</span>
      </nav>

      {project.isPending && <Skeleton className="h-24 w-full max-w-lg" />}
      {project.error && <ApiErrorText error={project.error} />}
      {project.data && (
        <>
          <header className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1 space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {ru.project.workspace}
                </p>
                <h1 className="text-3xl font-semibold tracking-tight">{project.data.name}</h1>
                {project.data.description && (
                  <p className="max-w-2xl text-muted-foreground">{project.data.description}</p>
                )}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={
                    reportGenMut.isPending ||
                    reportRegenMut.isPending ||
                    reportPolling ||
                    reportHardBlocked ||
                    deleteProjectMut.isPending
                  }
                  onClick={() => reportRegenMut.mutate()}
                  title={ru.project.regenerateReportHint}
                >
                  {reportRegenMut.isPending || reportPolling ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-2 size-4" />
                  )}
                  {reportRegenMut.isPending || reportPolling
                    ? ru.project.regenerateReportQueueing
                    : ru.project.regenerateReport}
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={deleteProjectMut.isPending || reportGenMut.isPending || reportRegenMut.isPending}
                  onClick={() => {
                    if (window.confirm(ru.project.deleteProjectConfirm)) {
                      deleteProjectMut.mutate();
                    }
                  }}
                >
                  {deleteProjectMut.isPending ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : null}
                  {ru.project.deleteProject}
                </Button>
              </div>
            </div>
            {(reportRegenMut.error || deleteProjectMut.error) && (
              <ApiErrorText error={reportRegenMut.error || deleteProjectMut.error} />
            )}
          </header>

          <ProgressSteps
            hasData={hasData}
            touchedProcessing={touchedProcessing}
            hasReport={hasReport}
            hasSummary={hasSummary}
          />

          {processingBanner && poll && (
            <Alert>
              <Loader2 className="size-4 animate-spin" />
              <AlertDescription>{pollBannerText(poll)}</AlertDescription>
            </Alert>
          )}

          <Tabs value={workspaceTab} onValueChange={setWorkspaceTab} className="space-y-6">
            <TabsList variant="line" className="h-auto min-h-10 w-full flex-wrap justify-start gap-1">
              <TabsTrigger value="report">{ru.project.tabReport}</TabsTrigger>
              <TabsTrigger value="data">{ru.project.tabData}</TabsTrigger>
              <TabsTrigger value="processing">{ru.project.tabProcessing}</TabsTrigger>
              <TabsTrigger value="quotes">{ru.project.tabQuotes}</TabsTrigger>
              <TabsTrigger value="external">{ru.project.tabExternal}</TabsTrigger>
              <TabsTrigger value="units">{ru.project.tabUnits}</TabsTrigger>
            </TabsList>

            <TabsContent value="data" className="mt-0 space-y-6">
          {/* Данные */}
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>{ru.project.dataSection}</CardTitle>
              <CardDescription>{ru.project.dataIntro}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <Collapsible>
                <CollapsibleTrigger
                  className={cn(
                    buttonVariants({ variant: 'ghost', size: 'sm' }),
                    'gap-1 px-0 text-muted-foreground',
                  )}
                >
                  <ChevronDown className="size-4" />
                  {ru.project.advanced}
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-3 space-y-3">
                  <p className="text-sm text-muted-foreground">{ru.project.advancedHint}</p>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">{ru.project.sourceTypeLabel}</span>
                    <Select
                      value={uploadSourceType}
                      onValueChange={(v) => setUploadSourceType(v as SourceType)}
                    >
                      <SelectTrigger className="max-w-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(Object.keys(SOURCE_TYPE_RU) as SourceType[]).map((t) => (
                          <SelectItem key={t} value={t}>
                            {SOURCE_TYPE_RU[t]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </CollapsibleContent>
              </Collapsible>

              <div className="flex flex-wrap gap-2">
                <label
                  className={cn(buttonVariants({ variant: 'outline' }), 'cursor-pointer')}
                >
                  {ru.project.uploadText}
                  <input
                    type="file"
                    className="sr-only"
                    accept=".txt,.md,text/*"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadTextMut.mutate(f);
                      e.target.value = '';
                    }}
                  />
                </label>
                <label
                  className={cn(buttonVariants({ variant: 'outline' }), 'cursor-pointer')}
                >
                  {ru.project.uploadAudio}
                  <input
                    type="file"
                    className="sr-only"
                    accept="audio/*"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadAudioMut.mutate({ file: f });
                      e.target.value = '';
                    }}
                  />
                </label>
              </div>
              {(uploadTextMut.error || uploadAudioMut.error) && (
                <ApiErrorText error={uploadTextMut.error || uploadAudioMut.error} />
              )}
              {(uploadTextMut.isSuccess || uploadAudioMut.isSuccess) && (
                <p className="text-sm text-muted-foreground">{ru.project.uploadOk}</p>
              )}

              <Separator />

              <Collapsible defaultOpen>
                <CollapsibleTrigger
                  className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), 'gap-1 px-0')}
                >
                  <ChevronDown className="size-4" />
                  {ru.project.noteBlockTitle}
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-4">
                  <form
                    className="grid max-w-xl gap-4"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (rawTitle.trim() && rawText.trim()) rawNoteMut.mutate();
                    }}
                  >
                    <div className="space-y-2">
                      <span className="text-sm font-medium">{ru.materials.titleField}</span>
                      <Input
                        value={rawTitle}
                        onChange={(e) => setRawTitle(e.target.value)}
                        placeholder={ru.project.noteTitlePh}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <span className="text-sm font-medium">{ru.project.noteBody}</span>
                      <Textarea
                        value={rawText}
                        onChange={(e) => setRawText(e.target.value)}
                        rows={4}
                        placeholder={ru.project.noteBodyPh}
                        required
                      />
                    </div>
                    <Button type="submit" variant="secondary" disabled={rawNoteMut.isPending}>
                      {rawNoteMut.isPending ? ru.project.savingNote : ru.project.saveNote}
                    </Button>
                    {rawNoteMut.error && <ApiErrorText error={rawNoteMut.error} />}
                  </form>
                </CollapsibleContent>
              </Collapsible>

              {sources.isPending && <Skeleton className="h-32 w-full" />}
              {sources.error && <ApiErrorText error={sources.error} />}
              {sources.data && (
                <>
                  {!sources.data.items.length ? (
                    <p className="text-sm text-muted-foreground">{ru.project.dataEmpty}</p>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">
                        {ru.common.totalCount(srcMeta?.total ?? 0)}
                      </p>
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>{ru.project.tableType}</TableHead>
                              <TableHead>{ru.project.tableName}</TableHead>
                              <TableHead>{ru.project.tableDate}</TableHead>
                              <TableHead>{ru.project.tableStatus}</TableHead>
                              <TableHead className="text-right">{ru.project.tableActions}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {sources.data.items.map((item) => (
                              <TableRow key={`${item.source_kind}-${item.id}`}>
                                <TableCell>
                                  {item.source_kind === 'document'
                                    ? ru.project.kindDocument
                                    : ru.project.kindAudio}
                                </TableCell>
                                <TableCell className="font-medium">{item.filename}</TableCell>
                                <TableCell className="text-muted-foreground">
                                  {fmtDate(item.created_at)}
                                </TableCell>
                                <TableCell className="text-sm text-muted-foreground">
                                  {sourceStatusForRow(item)}
                                </TableCell>
                                <TableCell className="text-right">
                                  {item.source_kind === 'document' ? (
                                    <Link
                                      to={`/sources/documents/${item.id}`}
                                      className={cn(buttonVariants({ variant: 'link' }), 'h-auto p-0')}
                                    >
                                      {ru.common.open}
                                    </Link>
                                  ) : (
                                    <Link
                                      to={`/sources/audios/${item.id}`}
                                      className={cn(buttonVariants({ variant: 'link' }), 'h-auto p-0')}
                                    >
                                      {ru.common.open}
                                    </Link>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={srcOffset <= 0}
                          onClick={() => setSrcOffset((o) => Math.max(0, o - PAGE))}
                        >
                          {ru.common.prev}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={!srcMeta || srcOffset + srcMeta.limit >= srcMeta.total}
                          onClick={() => setSrcOffset((o) => o + PAGE)}
                        >
                          {ru.common.next}
                        </Button>
                      </div>
                    </>
                  )}
                </>
              )}
            </CardContent>
          </Card>
            </TabsContent>

            <TabsContent value="processing" className="mt-0 space-y-6">

          {/* Обработка */}
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>{ru.project.processingSection}</CardTitle>
              <CardDescription>{ru.project.processingIntro}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <span className="text-sm font-medium">{ru.project.selectFile}</span>
                <Select
                  value={focusKey || FOCUS_NONE}
                  onValueChange={(v) => {
                    setFocusKey(v === FOCUS_NONE ? '' : (v ?? ''));
                    setPoll(null);
                  }}
                >
                  <SelectTrigger className="max-w-xl">
                    <SelectValue placeholder={ru.project.selectFilePh} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={FOCUS_NONE}>{ru.project.selectFilePh}</SelectItem>
                    {sources.data?.items.map((item) => (
                      <SelectItem key={item.id} value={`${item.source_kind}:${item.id}`}>
                        {item.source_kind === 'document' ? ru.project.kindDocument : ru.project.kindAudio}
                        {': '}
                        {item.filename}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-sm text-muted-foreground">{ru.project.selectFileHint}</p>
              </div>

              {focus?.kind === 'document' && detailDoc.isPending && (
                <div className="space-y-2">
                  <Skeleton className="h-8 w-64" />
                  <Skeleton className="h-10 w-full" />
                </div>
              )}
              {focus?.kind === 'document' && detailDoc.error && <ApiErrorText error={detailDoc.error} />}
              {focus?.kind === 'document' && d && (
                <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={docP.parts === 'done' ? 'default' : 'secondary'}>
                      {ru.project.statusParts}: {phaseLabel(docP.parts)}
                      {docP.parts === 'done' ? ` (${d.text_chunks_count})` : ''}
                    </Badge>
                    <Badge variant={docP.insights === 'done' ? 'default' : 'secondary'}>
                      {ru.project.statusInsights}: {phaseLabel(docP.insights)}
                      {docP.insights === 'done' ? ` (${d.extracted_entities_count})` : ''}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={extractDocMut.isPending}
                      onClick={() => extractDocMut.mutate()}
                    >
                      {extractDocMut.isPending || (poll?.t === 'ent' && poll.docId === focus.id) ? (
                        <Loader2 className="mr-2 size-4 animate-spin" />
                      ) : null}
                      {extractDocMut.isPending ? ru.project.insightsRunning : ru.project.getInsightsFile}
                    </Button>
                  </div>
                  {extractDocMut.error && <ApiErrorText error={extractDocMut.error} />}
                </div>
              )}

              {focus?.kind === 'audio' && detailAudio.isPending && <Skeleton className="h-24 w-full" />}
              {focus?.kind === 'audio' && detailAudio.error && <ApiErrorText error={detailAudio.error} />}
              {focus?.kind === 'audio' && a && (
                <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={audP.transcript === 'done' ? 'default' : 'secondary'}>
                      {ru.project.statusTranscript}: {phaseLabel(audP.transcript)}
                    </Badge>
                    <Badge variant={audP.parts === 'done' ? 'default' : 'secondary'}>
                      {ru.project.statusParts}: {phaseLabel(audP.parts)}
                      {audP.parts === 'done' ? ` (${a.text_chunks_count})` : ''}
                    </Badge>
                    <Badge variant={audP.insights === 'done' ? 'default' : 'secondary'}>
                      {ru.project.statusInsights}: {phaseLabel(audP.insights)}
                      {audP.insights === 'done' ? ` (${a.extracted_entities_count})` : ''}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      disabled={transcribeMut.isPending}
                      onClick={() => transcribeMut.mutate()}
                    >
                      {transcribeMut.isPending || (poll?.t === 'aud' && poll.audioId === focus.id) ? (
                        <Loader2 className="mr-2 size-4 animate-spin" />
                      ) : null}
                      {transcribeMut.isPending ? ru.project.transcribeRunning : ru.project.transcribe}
                    </Button>
                    {a.transcript?.id && (
                      <Button
                        disabled={extractTxMut.isPending}
                        onClick={() => extractTxMut.mutate(a.transcript!.id)}
                      >
                        {extractTxMut.isPending || poll?.t === 'txent' ? (
                          <Loader2 className="mr-2 size-4 animate-spin" />
                        ) : null}
                        {extractTxMut.isPending ? ru.project.insightsRunning : ru.project.insightsFromTranscript}
                      </Button>
                    )}
                  </div>
                  {(transcribeMut.error || extractTxMut.error) && (
                    <ApiErrorText error={transcribeMut.error || extractTxMut.error} />
                  )}
                </div>
              )}

              {!focus && (
                <p className="text-sm text-muted-foreground">{ru.project.noFileSelected}</p>
              )}

              <Separator />

              <div>
                <h3 className="mb-3 text-sm font-semibold">{ru.project.projectActions}</h3>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    disabled={aggregateMut.isPending}
                    onClick={() => aggregateMut.mutate()}
                  >
                    {aggregateMut.isPending || poll?.t === 'agg' ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : null}
                    {aggregateMut.isPending ? ru.project.aggregateQueueing : ru.project.aggregate}
                  </Button>
                  <Button
                    disabled={genSummaryMut.isPending}
                    onClick={() => genSummaryMut.mutate()}
                  >
                    {genSummaryMut.isPending || poll?.t === 'sum' ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : null}
                    {genSummaryMut.isPending ? ru.project.generateSummaryQueueing : ru.project.generateSummary}
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={
                      reportGenMut.isPending ||
                      reportRegenMut.isPending ||
                      reportPolling ||
                      reportHardBlocked ||
                      deleteProjectMut.isPending
                    }
                    onClick={() => reportGenMut.mutate()}
                  >
                    {reportGenMut.isPending || reportPolling ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : null}
                    {reportGenMut.isPending || reportPolling
                      ? ru.project.generateResearchReportQueueing
                      : ru.project.generateResearchReport}
                  </Button>
                </div>
                {(aggregateMut.error || genSummaryMut.error || reportGenMut.error || reportRegenMut.error) && (
                  <ApiErrorText
                    error={
                      aggregateMut.error ||
                      genSummaryMut.error ||
                      reportGenMut.error ||
                      reportRegenMut.error
                    }
                  />
                )}
              </div>

              {aggregation.data?.snapshot && (
                <Collapsible>
                  <CollapsibleTrigger
                    className={cn(
                      buttonVariants({ variant: 'ghost', size: 'sm' }),
                      'gap-1 px-0 text-muted-foreground',
                    )}
                  >
                    <ChevronDown className="size-4" />
                    {ru.project.lastAggregation}
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 space-y-2">
                    <p className="font-mono text-xs text-muted-foreground">
                      {aggregation.data.snapshot.created_at}
                    </p>
                    <div className="rounded-md border bg-muted/20 p-3 text-sm">
                      <AggregationPayloadView data={aggregation.data.snapshot.payload_json} />
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              )}
            </CardContent>
          </Card>

          {/* Части текста */}
          {focus?.kind === 'document' && d && (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle>{ru.project.chunksSection}</CardTitle>
                <CardDescription>{ru.project.chunksHint}</CardDescription>
              </CardHeader>
              <CardContent>
                {poll?.t === 'chunks' && poll.docId === focus.id && (
                  <div className="mb-4 space-y-2">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-5/6" />
                  </div>
                )}
                {(d.text_chunks_count ?? 0) === 0 ? (
                  <p className="text-sm text-muted-foreground">{ru.project.chunksEmpty}</p>
                ) : documentChunks.isPending ? (
                  <div className="space-y-2">
                    <Skeleton className="h-16 w-full" />
                    <Skeleton className="h-16 w-full" />
                  </div>
                ) : documentChunks.error ? (
                  <ApiErrorText error={documentChunks.error} />
                ) : (
                  <ul className="space-y-3">
                    {(documentChunks.data ?? []).map((ch) => {
                      const open = expandedChunks[ch.id] ?? false;
                      const preview = clipText(ch.text, 220);
                      return (
                        <li key={ch.id} className="rounded-lg border bg-card p-3 text-sm">
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <Badge variant="outline">#{ch.chunk_index + 1}</Badge>
                            {ch.token_count != null && (
                              <span className="text-xs">~{ch.token_count} tok</span>
                            )}
                          </div>
                          <p className="mt-2 whitespace-pre-wrap text-foreground">
                            {open ? ch.text : preview}
                          </p>
                          {ch.text.length > 220 && (
                            <Button
                              type="button"
                              variant="link"
                              className="mt-1 h-auto p-0 text-xs"
                              onClick={() =>
                                setExpandedChunks((m) => ({ ...m, [ch.id]: !open }))
                              }
                            >
                              {open ? ru.project.chunkCollapse : ru.project.chunkExpand}
                            </Button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}

            </TabsContent>

            <TabsContent value="report" className="mt-0 space-y-6">
              <Card className="shadow-sm border-primary/20">
                <CardHeader>
                  <CardTitle>{ru.project.tabReport}</CardTitle>
                  <CardDescription>{ru.project.reportTabIntro}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <PRReadinessCard
                    readiness={prReady}
                    isPending={readiness.isPending}
                    error={readiness.error}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      disabled={
                        reportGenMut.isPending ||
                        reportRegenMut.isPending ||
                        reportPolling ||
                        reportHardBlocked ||
                        deleteProjectMut.isPending
                      }
                      onClick={() => reportGenMut.mutate()}
                    >
                      {reportGenMut.isPending || reportPolling ? (
                        <Loader2 className="mr-2 size-4 animate-spin" />
                      ) : null}
                      {reportGenMut.isPending || reportPolling
                        ? ru.project.generateResearchReportQueueing
                        : ru.project.generateResearchReport}
                    </Button>
                  </div>
                  {(reportGenMut.error || reportRegenMut.error) && (
                    <ApiErrorText error={reportGenMut.error || reportRegenMut.error} />
                  )}

                  {projectReport.isPending && (
                    <div className="space-y-2">
                      <Skeleton className="h-8 w-1/2" />
                      <Skeleton className="h-40 w-full" />
                    </div>
                  )}
                  {projectReport.error && <ApiErrorText error={projectReport.error} />}

                  {!projectReport.isPending &&
                    !projectReport.error &&
                    (!projectReport.data?.report ||
                      projectReport.data.report.status === 'draft') && (
                      <p className="text-sm text-muted-foreground">{ru.project.reportEmpty}</p>
                    )}

                  {projectReport.data?.report?.status === 'generating' && (
                    <Alert>
                      <Loader2 className="size-4 animate-spin" />
                      <AlertDescription>{reportStageText(projectReport.data.report)}</AlertDescription>
                    </Alert>
                  )}

                  {projectReport.data?.report?.status === 'failed' && (
                    <Alert variant="destructive">
                      <AlertDescription>
                        {ru.project.reportStatusFailed}
                        <br />
                        {ru.project.reportFailureReason}: {reportFailureText(projectReport.data.report)}
                      </AlertDescription>
                    </Alert>
                  )}

                  {projectReport.data?.report?.status === 'ready' && (
                    <div className="space-y-6">
                      <ResearchReportView report={projectReport.data.report} />
                      <Collapsible>
                        <CollapsibleTrigger
                          className={cn(
                            buttonVariants({ variant: 'ghost', size: 'sm' }),
                            'h-auto gap-1 px-0 py-1 text-muted-foreground',
                          )}
                        >
                          <ChevronDown className="size-4" />
                          {ru.project.outcomeSection}
                        </CollapsibleTrigger>
                        <CollapsibleContent className="space-y-4 pt-2">
                          <p className="text-xs text-muted-foreground">{ru.project.outcomeIntro}</p>
                          {summary.isPending && (
                            <div className="space-y-2">
                              <Skeleton className="h-6 w-2/3" />
                              <Skeleton className="h-32 w-full" />
                            </div>
                          )}
                          {summary.error && <ApiErrorText error={summary.error} />}
                          {summary.data === null && !summary.isPending && (
                            <p className="text-sm text-muted-foreground">{ru.project.outcomeEmpty}</p>
                          )}
                          {summary.data && <SummaryOutcome summary={summary.data} />}
                        </CollapsibleContent>
                      </Collapsible>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="quotes" className="mt-0 space-y-6">
              <Card className="shadow-sm">
                <CardHeader>
                  <CardTitle>{ru.project.tabQuotes}</CardTitle>
                  <CardDescription>{ru.project.quotesTabIntro}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {projectReport.data?.report?.status !== 'ready' ? (
                    <p className="text-sm text-muted-foreground">{ru.project.quotesEmpty}</p>
                  ) : (() => {
                      const items = projectReport.data!.report!.supporting_quotes_json;
                      const arr = Array.isArray(items) ? items : [];
                      if (!arr.length) {
                        return (
                          <p className="text-sm text-muted-foreground">{ru.project.reportQuotesNone}</p>
                        );
                      }
                      return (
                        <ul className="space-y-4">
                          {arr.map((row, i) => {
                            const o =
                              typeof row === 'object' && row !== null && !Array.isArray(row)
                                ? (row as Record<string, unknown>)
                                : null;
                            const quote =
                              (o && typeof o.quote === 'string' && o.quote) ||
                              (o && typeof o.text === 'string' && o.text) ||
                              (typeof row === 'string' ? row : JSON.stringify(row));
                            const note = o && typeof o.note === 'string' ? o.note : null;
                            const entityId =
                              o && typeof o.entity_id === 'string' ? o.entity_id : null;
                            return (
                              <li
                                key={i}
                                className="rounded-lg border border-l-4 border-l-primary/40 bg-card p-4 text-sm"
                              >
                                <blockquote className="whitespace-pre-wrap text-foreground leading-relaxed">
                                  {quote}
                                </blockquote>
                                {note && (
                                  <p className="mt-2 text-xs text-muted-foreground">{note}</p>
                                )}
                                {entityId && (
                                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                                    entity_id: {entityId}
                                  </p>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      );
                    })()}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="external" className="mt-0 space-y-6">
              <Card className="shadow-sm">
                <CardHeader>
                  <CardTitle>{ru.project.tabExternal}</CardTitle>
                  <CardDescription>{ru.project.externalTabIntro}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {projectReport.data?.report?.status !== 'ready' ? (
                    <p className="text-sm text-muted-foreground">{ru.project.externalAwaitReport}</p>
                  ) : (() => {
                      const items = projectReport.data!.report!.external_articles_json;
                      const arr = Array.isArray(items) ? items : [];
                      if (!arr.length) {
                        return (
                          <p className="text-sm text-muted-foreground">{ru.project.externalEmpty}</p>
                        );
                      }
                      return (
                        <ul className="space-y-4">
                          {arr.map((row, i) => {
                            const o =
                              typeof row === 'object' && row !== null && !Array.isArray(row)
                                ? (row as Record<string, unknown>)
                                : null;
                            const title =
                              (o && typeof o.title === 'string' && o.title) ||
                              `Материал ${i + 1}`;
                            const url = o && typeof o.url === 'string' ? o.url : '';
                            const whyPr =
                              (o && typeof o.why_relevant_for_pr === 'string' && o.why_relevant_for_pr) ||
                              (o && typeof o.relevance === 'string' ? o.relevance : null);
                            const sum =
                              o && typeof o.summary === 'string' ? o.summary : null;
                            return (
                              <li key={i}>
                                <Card className="shadow-sm">
                                  <CardHeader className="pb-2">
                                    <CardTitle className="text-base leading-snug">
                                      {url ? (
                                        <a
                                          href={url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-primary underline-offset-4 hover:underline"
                                        >
                                          {title}
                                        </a>
                                      ) : (
                                        title
                                      )}
                                    </CardTitle>
                                    {whyPr && (
                                      <CardDescription className="text-sm text-foreground/90">
                                        <span className="font-medium text-muted-foreground">
                                          {ru.project.externalWhyPr}:{' '}
                                        </span>
                                        {whyPr}
                                      </CardDescription>
                                    )}
                                  </CardHeader>
                                  {sum && (
                                    <CardContent className="pt-0 text-sm text-muted-foreground">
                                      {sum}
                                    </CardContent>
                                  )}
                                </Card>
                              </li>
                            );
                          })}
                        </ul>
                      );
                    })()}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="units" className="mt-0 space-y-6">
          {/* Инсайты */}
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>{ru.project.insightsSection}</CardTitle>
              <CardDescription>{ru.project.insightsIntro}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-4">
                <div className="space-y-2">
                  <span className="text-sm font-medium">{ru.project.filterType}</span>
                  <Select
                    value={entityType || 'all'}
                    onValueChange={(v) => {
                      setEntityType(v === 'all' ? '' : (v as EntityType));
                      setEntOffset(0);
                    }}
                  >
                    <SelectTrigger className="w-[220px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{ru.project.filterAny}</SelectItem>
                      {PRIMARY_RESEARCH_FILTER_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {ENTITY_TYPE_RU[t]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <span className="text-sm font-medium">{ru.project.filterConfidence}</span>
                  <Input
                    className="w-36"
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={minConfidence}
                    placeholder={ru.project.filterConfidencePh}
                    onChange={(e) => {
                      setMinConfidence(e.target.value);
                      setEntOffset(0);
                    }}
                  />
                </div>
                <label className="flex cursor-pointer items-end gap-2 pb-1 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    className="size-4 rounded border border-input accent-primary"
                    checked={showAllEntityTypes}
                    onChange={(e) => {
                      setShowAllEntityTypes(e.target.checked);
                      setEntOffset(0);
                    }}
                  />
                  {ru.project.showAllEntityTypes}
                </label>
              </div>

              {entities.isPending && (
                <div className="space-y-3">
                  <Skeleton className="h-24 w-full" />
                  <Skeleton className="h-24 w-full" />
                </div>
              )}
              {entities.error && <ApiErrorText error={entities.error} />}
              {entities.data && (
                <>
                  {!entities.data.items.length ? (
                    <div className="rounded-lg border border-dashed p-8 text-center">
                      <p className="text-sm text-muted-foreground">{ru.project.insightsEmpty}</p>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm text-muted-foreground">
                        {ru.common.totalCount(entMeta?.total ?? 0)}
                      </p>
                      <ul className="space-y-4">
                        {entities.data.items.map((e) => {
                          const quote = evidenceQuoteFromJson(e.evidence_json);
                          const conf = e.confidence_score;
                          const prImp = (e.pr_implication ?? '').trim();
                          const msgGuide = (e.messaging_guidance ?? '').trim();
                          const headline = clipText(e.title?.trim() ? e.title : e.content, 160);
                          const bodyExtra =
                            e.title?.trim() && e.content.trim() && e.title.trim() !== e.content.trim()
                              ? clipText(e.content, 120)
                              : null;
                          return (
                            <li key={e.id}>
                              <Card className="shadow-sm">
                                <CardHeader className="pb-2">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge>{ENTITY_TYPE_RU[e.entity_type]}</Badge>
                                    {typeof conf === 'number' && !Number.isNaN(conf) && (
                                      <span className="text-xs text-muted-foreground">
                                        {ru.analytics.confidence}: {formatConfidence(conf)}
                                      </span>
                                    )}
                                  </div>
                                  {typeof conf === 'number' && (
                                    <Progress className="mt-2 h-1.5" value={Math.round(conf * 100)} />
                                  )}
                                  <CardTitle className="text-base leading-snug">{headline}</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2 text-sm">
                                  {bodyExtra && (
                                    <p className="text-muted-foreground">{bodyExtra}</p>
                                  )}
                                  {prImp ? (
                                    <p className="text-sm text-foreground/90">
                                      <span className="font-medium text-muted-foreground">
                                        {ru.project.entityPrImplication}:{' '}
                                      </span>
                                      {clipText(prImp, 320)}
                                    </p>
                                  ) : null}
                                  {msgGuide ? (
                                    <p className="text-sm text-foreground/90">
                                      <span className="font-medium text-muted-foreground">
                                        {ru.project.entityMessagingGuidance}:{' '}
                                      </span>
                                      {clipText(msgGuide, 320)}
                                    </p>
                                  ) : null}
                                  {quote && (
                                    <blockquote className="border-l-2 border-primary/30 pl-3 text-muted-foreground italic">
                                      {clipText(quote, 220)}
                                    </blockquote>
                                  )}
                                  <div className="flex flex-wrap gap-3">
                                    {e.source_document_id && (
                                      <Link
                                        to={`/sources/documents/${e.source_document_id}`}
                                        className="text-primary underline-offset-4 hover:underline"
                                      >
                                        {ru.project.insightSourceDoc}
                                      </Link>
                                    )}
                                    {e.source_audio_id && (
                                      <Link
                                        to={`/sources/audios/${e.source_audio_id}`}
                                        className="text-primary underline-offset-4 hover:underline"
                                      >
                                        {ru.project.insightSourceAudio}
                                      </Link>
                                    )}
                                  </div>
                                  <Collapsible>
                                    <CollapsibleTrigger
                                      className={cn(
                                        buttonVariants({ variant: 'ghost', size: 'sm' }),
                                        'h-8 px-0 text-xs',
                                      )}
                                    >
                                      {ru.project.insightMeta}
                                    </CollapsibleTrigger>
                                    <CollapsibleContent>
                                      <p className="font-mono text-xs text-muted-foreground">id {e.id}</p>
                                    </CollapsibleContent>
                                  </Collapsible>
                                </CardContent>
                              </Card>
                            </li>
                          );
                        })}
                      </ul>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={entOffset <= 0}
                          onClick={() => setEntOffset((o) => Math.max(0, o - PAGE))}
                        >
                          {ru.common.prev}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={!entMeta || entOffset + entMeta.limit >= entMeta.total}
                          onClick={() => setEntOffset((o) => o + PAGE)}
                        >
                          {ru.common.next}
                        </Button>
                      </div>
                    </>
                  )}
                </>
              )}
            </CardContent>
          </Card>
            </TabsContent>

          </Tabs>
        </>
      )}
    </div>
  );
}

function AggregationPayloadView({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (!entries.length) return <span className="text-muted-foreground">—</span>;
  return (
    <dl className="grid gap-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
          <dt className="shrink-0 font-medium text-foreground">{k}</dt>
          <dd className="min-w-0 break-words text-muted-foreground">
            {typeof v === 'object' && v !== null ? JSON.stringify(v, null, 2) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
