// @ts-nocheck — DEPRECATED: route redirects to ProjectDetailPage. Kept for widget reuse during migration.
// Batch dashboards / LLM bundles are loosely typed JSON until OpenAPI covers full shapes.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  addBatchSource,
  bulkUploadBatchSources,
  downloadBatchReportExcel,
  downloadBatchReportPpt,
  getAudiencePortrait,
  getBatchFullReport,
  getBatchSegmentCompare,
  getBatchScenarioReport,
  getPRStrategy,
  getBatch,
  getBatchAudioPipeline,
  getBatchCorpus,
  batchChartSvgUrl,
  batchDashboardQueryKey,
  downloadBatchDashboardCsv,
  downloadBatchDashboardPack,
  getBatchDashboard,
  postMessageLabAnalyze,
  getBatchInterviewUnits,
  getProject,
  listProjectSources,
  patchResearchBatch,
  queueBatchReportGenerate,
  removeBatchSource,
} from '../api/api';
import type {
  BatchDashboardTraced,
  DocumentPipelineRow,
  MessageLabAnalyzeResponse,
  OutputLanguage,
  PortraitFieldKey,
  PortraitGroundingEvidence,
  PortraitGroundingItem,
  ReportMode,
  SampleQuoteItem,
  TracedLabelRow,
  TracedSourceRef,
  UnifiedSourcesResponse,
} from '../api/types';
import { ApiErrorText } from '../components/ApiErrorText';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ru } from '../i18n/ru';
import { qk } from '../queryKeys';
import { cn } from '@/lib/utils';
import { isBatchPipelineIncomplete } from '@/features/batch/processingGate';
import { normalizeOutputLanguage } from '../utils/outputLanguage';
import {
  BatchDashboardResearchWidgets,
  PrRiskTrendIcon,
  evidenceRefHref,
} from '../components/BatchDashboardResearchWidgets';
import {
  BatchAiProcessingGateCard,
  BatchProcessingProgressSection,
} from '../components/BatchProcessingProgressSection';
import {
  Copy,
  Download,
  Loader2,
  Upload,
  ChevronDown,
  FileText,
  X,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  Tags,
} from 'lucide-react';

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}
const PAGE = 100;

const AGE_PRESETS = ['18–24', '25–34', '35–44', '45–54', '55+'] as const;

const GENDER_OPTS = [
  { value: 'female', label: 'Женский' },
  { value: 'male', label: 'Мужской' },
  { value: 'non-binary', label: 'Небинарный' },
  { value: 'prefer_not_say', label: 'Не указано' },
] as const;

const SEGMENT_PRESETS = [
  { value: 'student', label: 'Студент' },
  { value: 'mobile-first', label: 'Mobile-first' },
  { value: 'urban', label: 'Город' },
  { value: 'rural', label: 'Сельская местность' },
  { value: 'SMB', label: 'Малый/средний бизнес' },
  { value: 'enterprise', label: 'Крупный бизнес' },
] as const;

const TYPE_OPTS = [
  { value: 'depth', label: 'Глубинное' },
  { value: 'expert', label: 'Экспертное' },
  { value: 'usability', label: 'Юзабилити' },
  { value: 'diary', label: 'Дневник' },
  { value: 'other', label: 'Другое' },
] as const;

const LANG_OPTS = [
  { value: 'uz', label: 'Узбекский' },
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'Английский' },
] as const;

const COMPARE_GROUP_OPTS = [
  { value: 'gender', label: 'Пол' },
  { value: 'age_range', label: 'Возраст' },
  { value: 'segments', label: 'Сегменты' },
  { value: 'language', label: 'Язык' },
  { value: 'city', label: 'Город' },
  { value: 'interview_type', label: 'Тип интервью' },
  { value: 'date', label: 'Дата' },
  { value: 'interview_unit', label: 'Отдельное интервью' },
] as const;

const GROUP_BY_OPTS = [
  { value: '', label: 'Все интервью' },
  { value: 'gender', label: 'Пол' },
  { value: 'age_range', label: 'Возраст' },
  { value: 'segments', label: 'Сегменты' },
  { value: 'language', label: 'Язык' },
  { value: 'city', label: 'Город' },
  { value: 'interview_type', label: 'Тип интервью' },
  { value: 'date', label: 'Дата' },
] as const;

function sourceKey(item: UnifiedSourcesResponse['items'][number]): string {
  if (item.source_kind === 'document') return `doc:${item.id}`;
  return `audio:${item.id}`;
}

function BulletList({ items }: { items: string[] }) {
  if (!items?.length) {
    return <p className="text-sm text-muted-foreground">—</p>;
  }
  return (
    <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
}

function FreqChips({
  rows,
  limit = 8,
}: {
  rows: Array<Record<string, unknown>>;
  limit?: number;
}) {
  const slice = (rows || []).slice(0, limit);
  if (!slice.length) {
    return <p className="text-sm text-muted-foreground">—</p>;
  }
  return (
    <ul className="space-y-1 text-xs">
      {slice.map((r, i) => (
        <li key={i} className="flex justify-between gap-2 border-b border-border/40 py-1 last:border-0">
          <span className="min-w-0 truncate">{String(r.label ?? '')}</span>
          <span className="shrink-0 tabular-nums text-muted-foreground">{String(r.value ?? '')}</span>
        </li>
      ))}
    </ul>
  );
}

type DecisionLayerInput = {
  priority_actions?: Array<{
    action: string;
    impact: string;
    effort: string;
    reason: string;
  }>;
  impact_effort_matrix?: Array<{ action: string; impact: string; effort: string }>;
  alerts?: Array<{ type: string; message: string; severity: string }>;
};

function DecisionLayerPanel({
  priority_actions = [],
  impact_effort_matrix = [],
  alerts = [],
}: DecisionLayerInput) {
  const matrixRows =
    (impact_effort_matrix?.length ?? 0) > 0
      ? (impact_effort_matrix ?? [])
      : (priority_actions ?? []).map((p) => ({
          action: p.action,
          impact: p.impact,
          effort: p.effort,
        }));
  const has =
    (priority_actions?.length ?? 0) > 0 ||
    (alerts?.length ?? 0) > 0 ||
    matrixRows.length > 0;
  if (!has) return null;
  return (
    <div className="space-y-4">
      <Separator />
      <h3 className="text-lg font-semibold tracking-tight">{ru.batch.decisionLayerTitle}</h3>
      {(alerts?.length ?? 0) > 0 && (
        <Card className="shadow-sm border-amber-500/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ru.batch.decisionAlerts}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(alerts ?? []).map((a, i) => (
              <div
                key={i}
                className="flex flex-wrap items-start gap-2 rounded-md border bg-muted/20 p-3 text-sm"
              >
                <Badge variant={a.severity === 'high' ? 'destructive' : 'secondary'}>{a.type}</Badge>
                <Badge variant="outline">{a.severity}</Badge>
                <p className="min-w-0 flex-1 leading-relaxed">{a.message}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {(priority_actions?.length ?? 0) > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ru.batch.decisionPriorityActions}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(priority_actions ?? []).map((p, i) => (
              <div key={i} className="rounded-md border p-3 text-sm">
                <p className="font-medium text-foreground">{p.action}</p>
                <p className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span>
                    {ru.batch.decisionImpact}: <Badge variant="outline">{p.impact}</Badge>
                  </span>
                  <span>
                    {ru.batch.decisionEffort}: <Badge variant="outline">{p.effort}</Badge>
                  </span>
                </p>
                {p.reason ? (
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    <span className="font-medium text-foreground/80">{ru.batch.decisionReason}: </span>
                    {p.reason}
                  </p>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {matrixRows.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ru.batch.decisionMatrix}</CardTitle>
          </CardHeader>
          <CardContent className="p-0 sm:px-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{ru.batch.decisionActionColumn}</TableHead>
                  <TableHead className="w-24">{ru.batch.decisionImpact}</TableHead>
                  <TableHead className="w-24">{ru.batch.decisionEffort}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {matrixRows.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-sm">{row.action}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.impact}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.effort}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function formatDistValue(v: unknown): string {
  if (v != null && typeof v === 'object' && !Array.isArray(v)) {
    return Object.entries(v as Record<string, unknown>)
      .map(([a, b]) => `${a}: ${formatDistValue(b)}`)
      .join(', ');
  }
  if (Array.isArray(v)) {
    return v.map((x) => formatDistValue(x)).join(', ');
  }
  return String(v ?? '—');
}

function formatSegmentSnapshot(s: Record<string, unknown> | null | undefined): string {
  if (!s || typeof s !== 'object') {
    return '—';
  }
  return Object.entries(s)
    .map(([k, v]) => `${k}: ${formatDistValue(v)}`)
    .join(' · ');
}

function metaPreview(meta: Record<string, unknown>): string {
  try {
    const s = JSON.stringify(meta);
    return s.length > 120 ? `${s.slice(0, 120)}…` : s;
  } catch {
    return '—';
  }
}

function AnalysisStatsLine({
  confidence,
  dataCoverageScore,
  interviewCount,
  distribution,
  metaInterviewCount,
}: {
  confidence?: number;
  dataCoverageScore?: number;
  interviewCount?: number;
  distribution?: Record<string, unknown>;
  metaInterviewCount?: number;
}) {
  const ic =
    interviewCount ??
    (typeof metaInterviewCount === 'number' ? metaInterviewCount : undefined);
  const distEntries =
    distribution && Object.keys(distribution).length > 0
      ? Object.entries(distribution)
      : [];
  return (
    <div className="space-y-2 text-xs text-muted-foreground">
      <p className="flex flex-wrap gap-x-4 gap-y-1">
        {dataCoverageScore != null && (
          <span>
            {ru.batch.dataCoverageLabel}:{' '}
            <span className="font-medium text-foreground">
              {Math.round((Number.isFinite(dataCoverageScore) ? dataCoverageScore : 0) * 100)}%
            </span>
          </span>
        )}
        {confidence != null && (
          <span>
            {ru.batch.confidenceLabel}:{' '}
            <span className="font-medium text-foreground">
              {Math.round((Number.isFinite(confidence) ? confidence : 0) * 100)}%
            </span>
          </span>
        )}
        {ic != null && ic > 0 && (
          <span>
            {ru.batch.portraitMeta}: <span className="font-medium text-foreground">{ic}</span>{' '}
            {ru.batch.interviewCountShort}
          </span>
        )}
      </p>
      {distEntries.length > 0 && (
        <div>
          <p className="mb-1 font-medium text-foreground/80">
            {ru.batch.segmentDistributionLabel}
          </p>
          <ul className="flex flex-wrap gap-2">
            {distEntries.slice(0, 16).map(([k, v]) => (
              <li key={k}>
                <Badge variant="outline" className="max-w-full whitespace-normal text-left font-normal">
                  {k}: {formatDistValue(v)}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

async function invalidateBatchLlmQueries(
  qc: ReturnType<typeof useQueryClient>,
  batchId: string,
) {
  await qc.invalidateQueries({ queryKey: ['batchAudiencePortrait', batchId] });
  await qc.invalidateQueries({ queryKey: ['batchPrStrategy', batchId] });
  await qc.invalidateQueries({ queryKey: qk.batchFullReport(batchId) });
  await qc.invalidateQueries({ queryKey: ['batchSegmentCompare', batchId] });
  await qc.invalidateQueries({ queryKey: ['batchScenarioReport', batchId] });
  await qc.invalidateQueries({ queryKey: ['batchCorpus', batchId] });
  await qc.invalidateQueries({ queryKey: qk.batchInterviewUnits(batchId) });
  await qc.invalidateQueries({ queryKey: ['batchDashboard', batchId] });
  await qc.invalidateQueries({ queryKey: qk.batchAudioPipeline(batchId) });
}

function refLabelRefs(item: {
  entity_id?: string | null;
  source_document_id: string | null;
  source_audio_id: string | null;
  transcript_id: string | null;
  chunk_id?: string | null;
}): string {
  const bits: string[] = [];
  if (item.transcript_id) bits.push(`transcript: ${item.transcript_id.slice(0, 8)}…`);
  if (item.source_audio_id) bits.push(`audio: ${item.source_audio_id.slice(0, 8)}…`);
  if (item.source_document_id) bits.push(`doc: ${item.source_document_id.slice(0, 8)}…`);
  if (item.entity_id) bits.push(`entity: ${item.entity_id.slice(0, 8)}…`);
  if (item.chunk_id) bits.push(`chunk: ${item.chunk_id.slice(0, 8)}…`);
  return bits.join(' · ') || '—';
}

function traceNavHref(
  ref: TracedSourceRef,
): string | null {
  const n = ref.nav;
  if (!n) return null;
  if (n.kind === 'document' && n.document_id) {
    return `/sources/documents/${n.document_id}${n.chunk_id ? `?chunk=${encodeURIComponent(n.chunk_id)}` : ''}`;
  }
  if ((n.kind === 'audio' || n.kind === 'transcript') && n.audio_id) {
    return `/sources/audios/${n.audio_id}${n.chunk_id ? `?chunk=${encodeURIComponent(n.chunk_id)}` : ''}`;
  }
  return null;
}

function FieldGroundingList({ items }: { items: PortraitGroundingItem[] | undefined | null }) {
  const rows = items || [];
  if (rows.length === 0) return null;
  return (
    <div className="mt-4 space-y-3 border-t border-border/60 pt-3">
      <p className="text-xs font-medium text-muted-foreground">{ru.batch.evidenceForBlock}</p>
      {rows.map((row, j) => (
        <div key={j} className="space-y-2 text-xs">
          {row.insight ? <p className="text-foreground/90">{row.insight}</p> : null}
          {(row.evidence ?? []).map((e: PortraitGroundingEvidence, k: number) => (
            <blockquote
              key={k}
              className="border-l-2 border-primary/30 pl-2 text-muted-foreground leading-relaxed"
            >
              {e.quote}
              <p className="mt-1 font-mono text-[10px] text-muted-foreground/80">
                {refLabelRefs({
                  entity_id: e.entity_id,
                  source_document_id: e.source_document_id ?? null,
                  source_audio_id: e.source_audio_id ?? null,
                  transcript_id: e.transcript_id ?? null,
                })}
              </p>
            </blockquote>
          ))}
        </div>
      ))}
    </div>
  );
}

function DataQualityCallout({
  canSynthesize,
  warnings = [],
  title = ru.batch.dataQualityBlock,
  children,
}: {
  canSynthesize?: boolean;
  warnings?: string[];
  title?: string;
  children?: ReactNode;
}) {
  const w = (warnings || []).filter(Boolean);
  if (children == null && w.length === 0 && canSynthesize !== false) {
    return null;
  }
  return (
    <div
      className={cn(
        'space-y-2 rounded-md border p-3 text-sm',
        canSynthesize === false ? 'border-amber-500/35 bg-amber-500/5' : 'border-border/80 bg-muted/15',
      )}
    >
      <p className="font-medium text-foreground">{title}</p>
      {canSynthesize === false ? (
        <p className="text-xs text-amber-900/90 dark:text-amber-100/85">{ru.batch.synthesisBlockedTitle}</p>
      ) : null}
      {children}
      {w.length > 0 && (
        <ul className="list-disc space-y-1 pl-4 text-xs text-amber-900/90 dark:text-amber-100/90">
          {w.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SynthesisTextBanner({ message, blocked }: { message?: string | null; blocked?: boolean }) {
  if (!message && !blocked) return null;
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3 text-sm text-foreground">
      {blocked ? <p className="font-medium">{ru.batch.synthesisBlockedTitle}</p> : null}
      {message ? <p className="mt-1 text-muted-foreground leading-relaxed">{message}</p> : null}
    </div>
  );
}

function TracedRowsBlock({ title, rows }: { title: string; rows: TracedLabelRow[] }) {
  if (!rows.length) {
    return null;
  }
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold uppercase text-muted-foreground">{title}</h4>
      <ul className="space-y-2 text-xs">
        {rows.map((r, i) => (
          <li key={i} className="rounded-md border bg-background/50 p-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium text-foreground">{r.label}</span>
              <span className="shrink-0 text-muted-foreground">
                {ru.batch.timesMentioned(r.count)} · {r.pr_signal_type || r.entity_type}
              </span>
            </div>
            <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
              {ru.batch.sourceRefIds}: {r.source_refs?.slice(0, 3).map(refLabelRefs).join(' | ') || '—'}
            </p>
            {(() => {
              const f = r.source_refs[0];
              const h = f ? traceNavHref(f) : null;
              if (!h) return null;
              return (
                <p className="mt-1">
                  <Link to={h} className="text-xs font-medium text-primary underline-offset-2 hover:underline">
                    {ru.batch.openTracedSource}
                  </Link>
                </p>
              );
            })()}
          </li>
        ))}
      </ul>
    </div>
  );
}

function TracedTraceability({ traced }: { traced: BatchDashboardTraced | undefined }) {
  if (!traced) return null;
  const t = (traced.topics?.length ?? 0) + (traced.problems?.length ?? 0) + (traced.risks?.length ?? 0);
  if (t < 1) return null;
  return (
    <Collapsible className="rounded-md border bg-muted/10">
      <CollapsibleTrigger
        className={cn(
          buttonVariants({ variant: 'ghost', size: 'sm' }),
          'h-auto w-full justify-between gap-2 px-3 py-2 text-left',
        )}
      >
        <span className="text-sm font-medium">{ru.batch.traceabilityTitle}</span>
        <ChevronDown className="size-4 shrink-0" />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4 px-3 pb-3">
        <TracedRowsBlock title={ru.batch.tracedTopics} rows={traced.topics ?? []} />
        <TracedRowsBlock title={ru.batch.tracedProblems} rows={traced.problems ?? []} />
        <TracedRowsBlock title={ru.batch.tracedRisks} rows={traced.risks ?? []} />
      </CollapsibleContent>
    </Collapsible>
  );
}

function SampleQuotesList({ items = [] as SampleQuoteItem[] }: { items: SampleQuoteItem[] }) {
  if (!items?.length) return null;
  return (
    <Card className="shadow-sm border-dashed">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{ru.batch.sampleQuotesTitle}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((q, i) => (
          <div key={i} className="rounded-md border bg-muted/10 p-3 text-sm">
            {q.title ? <p className="text-xs font-medium text-foreground/90">{q.title}</p> : null}
            <p className="mt-1 whitespace-pre-wrap text-muted-foreground leading-relaxed">{q.text}</p>
            <p className="mt-2 text-[10px] font-mono text-muted-foreground/90">
              {refLabelRefs({
                entity_id: q.entity_id,
                source_document_id: q.source_document_id ?? null,
                source_audio_id: q.source_audio_id ?? null,
                transcript_id: q.transcript_id ?? null,
              })}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function BatchDetailPage() {
  const { projectId = '', batchId = '' } = useParams<{ projectId: string; batchId: string }>();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [advancedTab, setAdvancedTab] = useState<
    'overview' | 'portrait' | 'prstrategy' | 'fullreport' | 'compare' | 'scenarios' | 'corpus'
  >('overview');
  const [corpusMaxChars, setCorpusMaxChars] = useState(120_000);
  const [corpusCopied, setCorpusCopied] = useState(false);
  const [scenarioMode, setScenarioMode] = useState<ReportMode>('pr_audit');
  const [dashGroupBy, setDashGroupBy] = useState<string>('');
  const [dashSegmentKey, setDashSegmentKey] = useState('');
  const [dashDateFrom, setDashDateFrom] = useState('');
  const [dashDateTo, setDashDateTo] = useState('');
  const [dashStopwords, setDashStopwords] = useState(false);

  const dashQueryOpts = useMemo(
    () => ({
      group_by: dashGroupBy || null,
      segment_key: dashSegmentKey || null,
      date_from: dashDateFrom || null,
      date_to: dashDateTo || null,
      stopwords: dashStopwords,
    }),
    [dashGroupBy, dashSegmentKey, dashDateFrom, dashDateTo, dashStopwords],
  );
  const [portraitGroupBy, setPortraitGroupBy] = useState<string>('');
  const [portraitSegment, setPortraitSegment] = useState<string>('');
  const [compareGroupBy, setCompareGroupBy] = useState<string>('gender');
  const [compareSegA, setCompareSegA] = useState<string>('');
  const [compareSegB, setCompareSegB] = useState<string>('');
  const [bulkFiles, setBulkFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [runAnalysis, setRunAnalysis] = useState(true);
  const [invalidateLlmCacheAfterBulk, setInvalidateLlmCacheAfterBulk] = useState(true);
  const [messageLabDraft, setMessageLabDraft] = useState('');
  const [messageLabResult, setMessageLabResult] = useState<MessageLabAnalyzeResponse | null>(null);
  const [language, setLanguage] = useState<string>('ru');
  const [city, setCity] = useState('');
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [interviewType, setInterviewType] = useState<string>('depth');
  const [ageCustom, setAgeCustom] = useState('');
  const [segmentCustom, setSegmentCustom] = useState('');
  const [selectedAges, setSelectedAges] = useState<Set<string>>(() => new Set());
  const [selectedGenders, setSelectedGenders] = useState<Set<string>>(() => new Set());
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(() => new Set());

  const batch = useQuery({
    queryKey: qk.batch(batchId),
    queryFn: () => getBatch(batchId),
    enabled: !!batchId,
    refetchInterval: (q) => {
      const s = q.state.data?.queue_summary;
      if (!s) return false;
      if ((s.pending ?? 0) > 0 || (s.processing ?? 0) > 0) return 4000;
      return false;
    },
  });

  const projectRow = useQuery({
    queryKey: qk.project(projectId),
    queryFn: () => getProject(projectId),
    enabled: !!projectId,
  });

  const patchBatchStudyMut = useMutation({
    mutationFn: (body: {
      output_language?: OutputLanguage | null;
      single_file_multi_interview_mode?: boolean;
    }) => patchResearchBatch(batchId, body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.batch(batchId) });
      await qc.invalidateQueries({ queryKey: qk.batchInterviewUnits(batchId) });
      await invalidateBatchLlmQueries(qc, batchId);
    },
  });

  const interviewUnits = useQuery({
    queryKey: qk.batchInterviewUnits(batchId),
    queryFn: () => getBatchInterviewUnits(batchId),
    enabled: !!batchId && batch.data?.single_file_multi_interview_mode !== false,
  });

  const recalcAllAiMut = useMutation({
    mutationFn: async () => {
      const [p, s, f] = await Promise.all([
        getAudiencePortrait(batchId, {
          group_by: portraitGroupBy || undefined,
          segment_value: portraitSegment || undefined,
          recalculate: true,
        }),
        getPRStrategy(batchId, {
          group_by: portraitGroupBy || undefined,
          segment_value: portraitSegment || undefined,
          recalculate: true,
        }),
        getBatchFullReport(batchId, { recalculate: true }),
      ]);
      return { p, s, f };
    },
    onSuccess: (data) => {
      qc.setQueryData(qk.batchAudiencePortrait(batchId, portraitGroupBy, portraitSegment), data.p);
      qc.setQueryData(qk.batchPrStrategy(batchId, portraitGroupBy, portraitSegment), data.s);
      qc.setQueryData(qk.batchFullReport(batchId), data.f);
    },
  });

  const dashboard = useQuery({
    queryKey: qk.batchDashboard(batchId, batchDashboardQueryKey(dashQueryOpts)),
    queryFn: () => getBatchDashboard(batchId, dashQueryOpts),
    enabled: !!batchId,
    refetchInterval: (q) => {
      const d = q.state.data?.data_readiness_diagnostics;
      if (d?.pipelines_still_running) return 4000;
      if (d && d.interviews_total > 0 && d.interviews_processed < d.interviews_total) return 4000;
      return false;
    },
  });

  const hasBatchAudio = useMemo(
    () => !!(batch.data?.sources ?? []).find((s) => s.source_audio_id),
    [batch.data?.sources],
  );

  const hasBatchSources = useMemo(
    () => (batch.data?.sources?.length ?? 0) > 0,
    [batch.data?.sources],
  );

  const audioPipelineQuery = useQuery({
    queryKey: qk.batchAudioPipeline(batchId),
    queryFn: () => getBatchAudioPipeline(batchId),
    enabled: !!batchId && hasBatchSources,
    refetchInterval: (q) => {
      const s = q.state.data?.summary;
      if (!s) return false;
      const hasErr = (s.errors_count ?? 0) > 0 || (s.failed ?? 0) > 0;
      const t = s.total_interviews ?? 0;
      const p = s.processed_interviews ?? 0;
      if ((s.in_progress ?? 0) > 0) return 4000;
      if (t > 0 && p < t) return 4000;
      if (hasErr) return false;
      return false;
    },
  });

  const corpusQuery = useQuery({
    queryKey: qk.batchCorpus(batchId, corpusMaxChars),
    queryFn: () => getBatchCorpus(batchId, corpusMaxChars),
    enabled: !!batchId && advancedTab === 'corpus',
  });

  const portraitDashOpts = useMemo(
    () => ({ group_by: portraitGroupBy || null }),
    [portraitGroupBy],
  );
  const portraitSegmentsDash = useQuery({
    queryKey: qk.batchDashboard(batchId, batchDashboardQueryKey(portraitDashOpts)),
    queryFn: () => getBatchDashboard(batchId, portraitDashOpts),
    enabled:
      !!batchId &&
      !!portraitGroupBy &&
      (advancedTab === 'portrait' || advancedTab === 'prstrategy'),
  });

  useEffect(() => {
    setPortraitSegment('');
  }, [portraitGroupBy]);

  useEffect(() => {
    setCompareSegA('');
    setCompareSegB('');
  }, [compareGroupBy]);

  const hasInterviewSources = useMemo(
    () => !!(batch.data?.sources ?? []).filter((s) => s.source_kind === 'document').length,
    [batch.data?.sources],
  );

  const dataReadiness = useQuery({
    queryKey: qk.batchDashboard(batchId, batchDashboardQueryKey({ group_by: null })),
    queryFn: () => getBatchDashboard(batchId, { group_by: null }),
    enabled: !!batchId,
    refetchInterval: (q) => {
      const d = q.state.data?.data_readiness_diagnostics;
      if (d?.pipelines_still_running) return 4000;
      if (d && d.interviews_total > 0 && d.interviews_processed < d.interviews_total) return 4000;
      return false;
    },
  });

  /**
   * Строгий гейт INSIGHT/ACTION: `strict_pr_ready === false` (пороги объёма данных).
   * Fallback на `can_synthesize_llm` для совместимости со старыми ответами API.
   */
  const strictPrBlocksAi = useMemo(() => {
    if (!dataReadiness.isSuccess || !dataReadiness.data?.data_quality) return false;
    const dq = dataReadiness.data.data_quality;
    if (typeof dq.strict_pr_ready === 'boolean') {
      return !dq.strict_pr_ready;
    }
    return dq.can_synthesize_llm === false;
  }, [dataReadiness.isSuccess, dataReadiness.data?.data_quality]);

  const processingPipelineIncomplete = useMemo(
    () =>
      isBatchPipelineIncomplete({
        sourcesLength: batch.data?.sources?.length ?? 0,
        queuePending: batch.data?.queue_summary?.pending ?? 0,
        queueProcessing: batch.data?.queue_summary?.processing ?? 0,
        diagnostics: dataReadiness.data?.data_readiness_diagnostics,
        audioItemsInFlight: (audioPipelineQuery.data?.items ?? []).some((it) => {
          const st = (it.overall_status || '').toLowerCase();
          return st !== 'ready' && st !== 'failed';
        }),
        audioInProgress: audioPipelineQuery.data?.summary?.in_progress ?? 0,
        interviewsTotal:
          audioPipelineQuery.data?.summary?.total_interviews ??
          dataReadiness.data?.data_readiness_diagnostics?.interviews_total ??
          0,
        interviewsProcessed:
          audioPipelineQuery.data?.summary?.processed_interviews ??
          dataReadiness.data?.data_readiness_diagnostics?.interviews_processed ??
          0,
      }),
    [
      batch.data?.sources?.length,
      batch.data?.queue_summary,
      dataReadiness.data?.data_readiness_diagnostics,
      audioPipelineQuery.data?.summary,
      audioPipelineQuery.data?.items,
    ],
  );

  const aiPipelineBlocksFeatures = strictPrBlocksAi || processingPipelineIncomplete;

  useEffect(() => {
    if (!strictPrBlocksAi) return;
    if (
      advancedTab === 'portrait' ||
      advancedTab === 'prstrategy' ||
      advancedTab === 'fullreport' ||
      advancedTab === 'scenarios' ||
      advancedTab === 'compare'
    ) {
      setAdvancedTab('overview');
    }
  }, [strictPrBlocksAi, advancedTab]);

  const onRefreshDashboard = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['batchDashboard', batchId] });
    void dataReadiness.refetch();
  }, [qc, batchId, dataReadiness]);

  const onRefreshProcessing = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['batchDashboard', batchId] });
    void dataReadiness.refetch();
    void dashboard.refetch();
    void audioPipelineQuery.refetch();
    void batch.refetch();
  }, [qc, batchId, dataReadiness, dashboard, audioPipelineQuery, batch]);

  const batchDocumentSources = useMemo(
    () => (batch.data?.sources ?? []).filter((s) => s.source_kind === 'document'),
    [batch.data?.sources],
  );

  const compareDashOpts = useMemo(
    () => ({
      group_by: compareGroupBy || null,
      compare_segment_a: compareSegA || null,
      compare_segment_b: compareSegB || null,
    }),
    [compareGroupBy, compareSegA, compareSegB],
  );
  const compareDash = useQuery({
    queryKey: qk.batchDashboard(batchId, batchDashboardQueryKey(compareDashOpts)),
    queryFn: () => getBatchDashboard(batchId, compareDashOpts),
    enabled: !!batchId && !!compareGroupBy && advancedTab === 'compare',
  });

  const compareReady =
    !!compareGroupBy && !!compareSegA && !!compareSegB && compareSegA !== compareSegB;

  const compareQuery = useQuery({
    queryKey: qk.batchSegmentCompare(batchId, compareGroupBy, compareSegA, compareSegB),
    queryFn: () =>
      getBatchSegmentCompare(batchId, {
        group_by: compareGroupBy,
        segment_a: compareSegA,
        segment_b: compareSegB,
      }),
    enabled:
      !!batchId &&
      hasInterviewSources &&
      advancedTab === 'compare' &&
      compareReady &&
      !aiPipelineBlocksFeatures,
  });

  const portraitQuery = useQuery({
    queryKey: qk.batchAudiencePortrait(batchId, portraitGroupBy, portraitSegment),
    queryFn: () =>
      getAudiencePortrait(batchId, {
        group_by: portraitGroupBy || undefined,
        segment_value: portraitSegment || undefined,
      }),
    enabled: !!batchId && hasInterviewSources && advancedTab === 'portrait' && !aiPipelineBlocksFeatures,
  });

  const portraitRecalc = useMutation({
    mutationFn: () =>
      getAudiencePortrait(batchId, {
        group_by: portraitGroupBy || undefined,
        segment_value: portraitSegment || undefined,
        recalculate: true,
      }),
    onSuccess: (data) => {
      qc.setQueryData(
        qk.batchAudiencePortrait(batchId, portraitGroupBy, portraitSegment),
        data,
      );
    },
  });

  const prStrategyQuery = useQuery({
    queryKey: qk.batchPrStrategy(batchId, portraitGroupBy, portraitSegment),
    queryFn: () =>
      getPRStrategy(batchId, {
        group_by: portraitGroupBy || undefined,
        segment_value: portraitSegment || undefined,
      }),
    enabled: !!batchId && hasInterviewSources && !aiPipelineBlocksFeatures,
  });

  const prStrategyRecalc = useMutation({
    mutationFn: () =>
      getPRStrategy(batchId, {
        group_by: portraitGroupBy || undefined,
        segment_value: portraitSegment || undefined,
        recalculate: true,
      }),
    onSuccess: (data) => {
      qc.setQueryData(qk.batchPrStrategy(batchId, portraitGroupBy, portraitSegment), data);
    },
  });

  const fullReportQuery = useQuery({
    queryKey: qk.batchFullReport(batchId),
    queryFn: () => getBatchFullReport(batchId),
    enabled: !!batchId && hasInterviewSources && advancedTab === 'fullreport' && !aiPipelineBlocksFeatures,
  });

  const fullReportRecalc = useMutation({
    mutationFn: () => getBatchFullReport(batchId, { recalculate: true }),
    onSuccess: (data) => {
      qc.setQueryData(qk.batchFullReport(batchId), data);
    },
  });

  const scenarioQuery = useQuery({
    queryKey: qk.batchScenarioReport(batchId, scenarioMode),
    queryFn: () => getBatchScenarioReport(batchId, scenarioMode),
    enabled: !!batchId && hasInterviewSources && advancedTab === 'scenarios' && !aiPipelineBlocksFeatures,
  });

  const sources = useQuery({
    queryKey: qk.sources(projectId, 0, PAGE),
    queryFn: () => listProjectSources(projectId, 0, PAGE),
    enabled: !!projectId,
  });

  const inBatch = useMemo(() => {
    const s = new Set<string>();
    for (const row of batch.data?.sources ?? []) {
      if (row.source_document_id) s.add(`doc:${row.source_document_id}`);
      if (row.source_audio_id) s.add(`audio:${row.source_audio_id}`);
    }
    return s;
  }, [batch.data?.sources]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  };

  const toggleInSet = (v: string, setter: Dispatch<SetStateAction<Set<string>>>) => {
    setter((prev) => {
      const n = new Set(prev);
      if (n.has(v)) n.delete(v);
      else n.add(v);
      return n;
    });
  };

  const buildMetadata = useCallback((): Record<string, unknown> => {
    const ages = [...selectedAges];
    if (ageCustom.trim()) ages.push(ageCustom.trim());
    const genders = [...selectedGenders];
    const segments = [...selectedSegments];
    if (segmentCustom.trim()) segments.push(segmentCustom.trim());
    const meta: Record<string, unknown> = {
      language: language || 'ru',
      city: city.trim() || undefined,
      date: date || undefined,
      interview_type: interviewType || undefined,
    };
    if (genders.length) meta.gender = genders.length === 1 ? genders[0]! : genders;
    if (ages.length) meta.age_range = ages.length === 1 ? ages[0]! : ages;
    if (segments.length) meta.segments = segments;
    return Object.fromEntries(Object.entries(meta).filter(([, v]) => v !== undefined && v !== ''));
  }, [
    selectedAges,
    selectedGenders,
    selectedSegments,
    ageCustom,
    segmentCustom,
    language,
    city,
    date,
    interviewType,
  ]);

  const addSelectedMut = useMutation({
    mutationFn: async () => {
      for (const key of selected) {
        if (inBatch.has(key)) continue;
        const [kind, id] = key.split(':') as [string, string];
        if (kind !== 'doc') continue;
        await addBatchSource(batchId, { source_document_id: id });
      }
    },
    onSuccess: async () => {
      setSelected(new Set());
      await qc.invalidateQueries({ queryKey: qk.batch(batchId) });
      await qc.invalidateQueries({ queryKey: ['batchDashboard', batchId] });
      await invalidateBatchLlmQueries(qc, batchId);
    },
  });

  const bulkMut = useMutation({
    mutationFn: async () => {
      if (bulkFiles.length === 0) return;
      return bulkUploadBatchSources(batchId, bulkFiles, buildMetadata(), runAnalysis, {
        invalidateLlmCache: invalidateLlmCacheAfterBulk,
      });
    },
    onSuccess: async () => {
      setBulkFiles([]);
      await qc.invalidateQueries({ queryKey: qk.batch(batchId) });
      await qc.invalidateQueries({ queryKey: ['batchDashboard', batchId] });
      await qc.invalidateQueries({ queryKey: qk.sources(projectId, 0, PAGE) });
      await qc.invalidateQueries({ queryKey: qk.projectBatches(projectId, 0, 50) });
      await invalidateBatchLlmQueries(qc, batchId);
    },
  });

  const removeMut = useMutation({
    mutationFn: (sourceRowId: string) => removeBatchSource(batchId, sourceRowId),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.batch(batchId) });
      await qc.invalidateQueries({ queryKey: ['batchDashboard', batchId] });
      await invalidateBatchLlmQueries(qc, batchId);
    },
  });

  const reportMut = useMutation({
    mutationFn: () => {
      const eff = normalizeOutputLanguage(
        (batch.data?.output_language as string | null | undefined) ??
          (projectRow.data?.output_language as string | undefined),
        'ru',
      );
      return queueBatchReportGenerate(batchId, { output_language: eff });
    },
  });

  const exportExcelMut = useMutation({ mutationFn: () => downloadBatchReportExcel(batchId) });
  const exportPptMut = useMutation({ mutationFn: () => downloadBatchReportPpt(batchId) });

  const messageLabMut = useMutation({
    mutationFn: async () => {
      const eff = normalizeOutputLanguage(
        (batch.data?.output_language as string | null | undefined) ??
          (projectRow.data?.output_language as string | undefined),
        'ru',
      );
      return postMessageLabAnalyze(batchId, {
        message: messageLabDraft,
        output_language: eff,
      });
    },
    onSuccess: (data) => {
      setMessageLabResult(data);
    },
  });

  const maxProblem = useMemo(() => {
    const rows = dashboard.data?.problems_bar ?? [];
    return Math.max(1, ...rows.map((r) => r.value));
  }, [dashboard.data?.problems_bar]);

  const topicTotal = useMemo(() => {
    const rows = dashboard.data?.topics_pie ?? [];
    return rows.reduce((a, r) => a + r.value, 0) || 1;
  }, [dashboard.data?.topics_pie]);

  const maxRisk = useMemo(() => {
    const rows = dashboard.data?.risks_bar ?? [];
    return Math.max(1, ...rows.map((r) => r.value));
  }, [dashboard.data?.risks_bar]);

  const onFiles = (list: FileList | File[]) => {
    const arr = Array.from(list)
      .filter(
        (f) =>
          /\.(txt|md|markdown|docx)$/i.test(f.name) ||
          (f.type &&
            (f.type.includes('text') ||
              f.type.includes('markdown') ||
              f.type.includes('wordprocessingml'))),
      )
      .slice(0, 100);
    setBulkFiles((prev) => [...prev, ...arr].slice(0, 100));
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-1 pb-10 sm:px-0">
      <nav className="text-sm text-muted-foreground">
        <Link to="/projects" className="font-medium text-foreground hover:underline">
          {ru.nav.projects}
        </Link>
        <span className="mx-2">/</span>
        <Link to={`/projects/${projectId}`} className="font-medium text-foreground hover:underline">
          {ru.batch.backToProject}
        </Link>
        <span className="mx-2">/</span>
        <span>{ru.batch.crumb}</span>
      </nav>

      {batch.isPending && <Skeleton className="h-16 w-full max-w-xl" />}
      {batch.error && <ApiErrorText error={batch.error} />}

      {batch.data && (
        <>
          <header className="space-y-3 border-b border-border/60 pb-6">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant="secondary" className="rounded-full px-3 py-1 text-xs font-medium">
                {ru.batch.crumb}
              </Badge>
              {batch.data.sources && batch.data.sources.length > 0 && (
                <Badge variant="outline" className="rounded-full px-3 py-1 text-xs font-normal">
                  {ru.batch.sourceCountLabel}:
                  <span className="ml-1 font-semibold tabular-nums">{batch.data.sources.length}</span>
                </Badge>
              )}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">{batch.data.name}</h1>
            {batch.data.description && (
              <p className="max-w-2xl text-muted-foreground leading-relaxed">{batch.data.description}</p>
            )}
          </header>

          <Card
            id="batch-bulk-data-stage"
            className="overflow-hidden border-border/80 shadow-sm scroll-mt-4"
          >
            <div className="bg-muted/30">
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      <Upload className="size-5" />
                    </div>
                    <div className="space-y-1">
                      <CardTitle className="text-xl">{ru.batch.bulkTitle}</CardTitle>
                      <CardDescription className="max-w-xl leading-relaxed">
                        {ru.batch.bulkHint}
                      </CardDescription>
                    </div>
                  </div>
                  {bulkFiles.length > 0 && (
                    <Badge
                      variant="default"
                      className="shrink-0 self-start rounded-full px-3 py-1 text-xs font-medium"
                    >
                      {ru.batch.selectedFiles}: {bulkFiles.length}
                    </Badge>
                  )}
                </div>
              </CardHeader>
            </div>
            <CardContent className="space-y-6 pt-6">
              <div
                role="button"
                tabIndex={0}
                aria-label={ru.batch.dropHere}
                className={cn(
                  'group relative flex min-h-[180px] cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-all',
                  'hover:border-primary/60 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                  dragOver
                    ? 'border-primary bg-primary/10 shadow-inner'
                    : 'border-muted-foreground/25 bg-muted/20',
                )}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  onFiles(e.dataTransfer.files);
                }}
                onClick={() => document.getElementById('batch-bulk-files')?.click()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    document.getElementById('batch-bulk-files')?.click();
                  }
                }}
              >
                <div
                  className={cn(
                    'flex size-12 items-center justify-center rounded-full transition-all',
                    dragOver
                      ? 'bg-primary/20 text-primary scale-110'
                      : 'bg-primary/10 text-primary group-hover:scale-105',
                  )}
                >
                  <Upload className="size-6" />
                </div>
                <p className="text-base font-medium text-foreground">{ru.batch.dropHere}</p>
                <p className="text-xs text-muted-foreground">{ru.batch.maxFiles}</p>
                <input
                  id="batch-bulk-files"
                  type="file"
                  multiple
                  className="hidden"
                  accept=".txt,.md,.markdown,.docx,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(e) => {
                    if (e.target.files) onFiles(e.target.files);
                    e.target.value = '';
                  }}
                />
              </div>

              {bulkFiles.length > 0 && (
                <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-muted-foreground">
                      {ru.batch.selectedFiles}: <span className="font-semibold text-foreground">{bulkFiles.length}</span>
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
                      onClick={() => setBulkFiles([])}
                    >
                      <X className="mr-1 size-3" />
                      {ru.batch.bulkClear}
                    </Button>
                  </div>
                  <ul className="grid max-h-[220px] gap-2 overflow-auto sm:grid-cols-2">
                    {bulkFiles.map((f, idx) => (
                      <li
                        key={`${f.name}-${idx}`}
                        className="flex items-center gap-2 rounded-md border bg-background/80 p-2 text-xs"
                      >
                        <FileText className="size-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-foreground" title={f.name}>
                            {f.name}
                          </p>
                          <p className="text-[11px] text-muted-foreground">{formatFileSize(f.size)}</p>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="size-7 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                          aria-label={ru.batch.bulkRemoveFileAria}
                          onClick={() =>
                            setBulkFiles((prev) => prev.filter((_, i) => i !== idx))
                          }
                        >
                          <X className="size-3.5" />
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <Collapsible>
                <CollapsibleTrigger
                  className={cn(
                    buttonVariants({ variant: 'outline', size: 'sm' }),
                    'group w-full justify-between gap-2',
                  )}
                >
                  <span className="inline-flex items-center gap-2">
                    <Tags className="size-4 text-muted-foreground" />
                    {ru.batch.bulkMetadataOptional}
                  </span>
                  <ChevronDown className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-5 pt-4">
                  <p className="text-xs text-muted-foreground">{ru.batch.applyToAllNote}</p>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaLanguage}
                      </label>
                      <select
                        className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30"
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                      >
                        {LANG_OPTS.map((l) => (
                          <option key={l.value} value={l.value}>
                            {l.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaCity}
                      </label>
                      <Input
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        placeholder="Ташкент"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaDate}
                      </label>
                      <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaInterviewType}
                      </label>
                      <select
                        className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30"
                        value={interviewType}
                        onChange={(e) => setInterviewType(e.target.value)}
                      >
                        {TYPE_OPTS.map((l) => (
                          <option key={l.value} value={l.value}>
                            {l.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2 sm:col-span-2 lg:col-span-2">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaGender}
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {GENDER_OPTS.map((g) => (
                          <Button
                            key={g.value}
                            type="button"
                            size="sm"
                            variant={selectedGenders.has(g.value) ? 'default' : 'outline'}
                            onClick={() => toggleInSet(g.value, setSelectedGenders)}
                          >
                            {g.label}
                          </Button>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-2 sm:col-span-2">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaAgeRange}
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {AGE_PRESETS.map((a) => (
                          <Button
                            key={a}
                            type="button"
                            size="sm"
                            variant={selectedAges.has(a) ? 'default' : 'outline'}
                            onClick={() => toggleInSet(a, setSelectedAges)}
                          >
                            {a}
                          </Button>
                        ))}
                      </div>
                      <Input
                        placeholder={ru.batch.ageCustomPlaceholder}
                        value={ageCustom}
                        onChange={(e) => setAgeCustom(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2 sm:col-span-2">
                      <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {ru.batch.metaSegments}
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {SEGMENT_PRESETS.map((a) => (
                          <Button
                            key={a.value}
                            type="button"
                            size="sm"
                            variant={selectedSegments.has(a.value) ? 'default' : 'outline'}
                            onClick={() => toggleInSet(a.value, setSelectedSegments)}
                          >
                            {a.label}
                          </Button>
                        ))}
                      </div>
                      <Input
                        placeholder={ru.batch.segmentCustomPlaceholder}
                        value={segmentCustom}
                        onChange={(e) => setSegmentCustom(e.target.value)}
                      />
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>

              <div className="grid gap-2 sm:grid-cols-2">
                <label
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm transition-colors',
                    runAnalysis ? 'border-primary/40 bg-primary/5' : 'border-border hover:bg-muted/30',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={runAnalysis}
                    onChange={(e) => setRunAnalysis(e.target.checked)}
                    className="mt-0.5 size-4 accent-primary"
                  />
                  <span className="flex items-start gap-2">
                    <Sparkles className="mt-0.5 size-4 shrink-0 text-primary/80" />
                    <span className="font-medium">{ru.batch.runAnalysis}</span>
                  </span>
                </label>
                <label
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm transition-colors',
                    invalidateLlmCacheAfterBulk
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-border hover:bg-muted/30',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={invalidateLlmCacheAfterBulk}
                    onChange={(e) => setInvalidateLlmCacheAfterBulk(e.target.checked)}
                    className="mt-0.5 size-4 accent-primary"
                  />
                  <span className="flex items-start gap-2">
                    <RefreshCw className="mt-0.5 size-4 shrink-0 text-primary/80" />
                    <span className="font-medium">{ru.batch.invalidateLlmCacheAfterBulk}</span>
                  </span>
                </label>
              </div>

              <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-4">
                {bulkFiles.length > 0 && (
                  <p className="mr-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CheckCircle2 className="size-4 text-emerald-600" />
                    {ru.batch.bulkReadyToUpload}{' '}
                    <span className="font-semibold text-foreground">{bulkFiles.length}</span>
                  </p>
                )}
                <Button
                  type="button"
                  size="lg"
                  className="gap-2"
                  disabled={bulkFiles.length === 0 || bulkMut.isPending}
                  onClick={() => bulkMut.mutate()}
                >
                  {bulkMut.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Upload className="size-4" />
                  )}
                  {ru.batch.uploadBulk}
                </Button>
              </div>
              {bulkMut.error && <ApiErrorText error={bulkMut.error} />}
            </CardContent>
          </Card>

          <div className="flex max-w-2xl flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{ru.batch.batchResearchOutputLabel}</p>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                {ru.batch.batchResearchOutputHint}
              </p>
            </div>
            <Select
              value={batch.data.output_language ?? '__inherit__'}
              onValueChange={(v) => {
                if (v === '__inherit__') patchBatchStudyMut.mutate({ output_language: null });
                else patchBatchStudyMut.mutate({ output_language: normalizeOutputLanguage(v as OutputLanguage) });
              }}
              disabled={patchBatchStudyMut.isPending}
            >
              <SelectTrigger className="w-full sm:w-[220px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__inherit__">{ru.batch.inheritProjectLanguage}</SelectItem>
                <SelectItem value="ru">{ru.project.reportLangRu}</SelectItem>
                <SelectItem value="uz">{ru.project.reportLangUz}</SelectItem>
                <SelectItem value="en">{ru.project.reportLangEn}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {patchBatchStudyMut.error && <ApiErrorText error={patchBatchStudyMut.error} />}

          <Collapsible className="max-w-3xl">
            <CollapsibleTrigger
              className={cn(
                buttonVariants({ variant: 'outline', size: 'sm' }),
                'group w-full justify-between gap-2 sm:w-auto',
              )}
            >
              <span>{ru.batch.batchSettingsToggle}</span>
              <ChevronDown className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3 space-y-3">
              <div className="flex max-w-xl flex-col gap-2 rounded-md border bg-muted/10 p-4">
                <label className="flex cursor-pointer items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1 size-4 accent-primary"
                    checked={batch.data.single_file_multi_interview_mode !== false}
                    onChange={(e) =>
                      patchBatchStudyMut.mutate({ single_file_multi_interview_mode: e.target.checked })
                    }
                    disabled={patchBatchStudyMut.isPending}
                  />
                  <span>
                    <span className="font-medium">{ru.batch.multiInterviewMode}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {ru.batch.multiInterviewHint}
                    </span>
                  </span>
                </label>
                <p className="text-xs text-muted-foreground">{ru.batch.pipelineHint}</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-fit"
                  disabled={recalcAllAiMut.isPending || !hasInterviewSources || aiPipelineBlocksFeatures}
                  onClick={() => recalcAllAiMut.mutate()}
                >
                  {recalcAllAiMut.isPending ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                  {ru.batch.recalculateAllAi}
                </Button>
                {recalcAllAiMut.error && <ApiErrorText error={recalcAllAiMut.error} />}
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  disabled={
                    reportMut.isPending || batchDocumentSources.length === 0 || aiPipelineBlocksFeatures
                  }
                  onClick={() => reportMut.mutate()}
                >
                  {reportMut.isPending ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : null}
                  {reportMut.isPending ? ru.batch.generatingReport : ru.batch.generateReport}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={exportExcelMut.isPending || exportPptMut.isPending}
                  onClick={() => exportExcelMut.mutate()}
                >
                  {exportExcelMut.isPending ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                  {ru.batch.downloadExcel}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={exportExcelMut.isPending || exportPptMut.isPending}
                  onClick={() => exportPptMut.mutate()}
                >
                  {exportPptMut.isPending ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                  {ru.batch.downloadPpt}
                </Button>
              </div>
            </CollapsibleContent>
          </Collapsible>
          {(reportMut.error || exportExcelMut.error || exportPptMut.error) && (
            <ApiErrorText
              error={reportMut.error || exportExcelMut.error || exportPptMut.error}
            />
          )}

          {strictPrBlocksAi && (
            <div
              className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm"
              role="status"
            >
              <p className="font-medium text-foreground">{ru.batch.dataStageBannerTitle}</p>
              <p className="text-muted-foreground leading-relaxed">{ru.batch.dataStageBannerBody}</p>
              {dataReadiness.data?.data_quality?.gates_checklist &&
              dataReadiness.data.data_quality.gates_checklist.length > 0 ? (
                <ul className="list-none space-y-1 border-t border-amber-500/20 pt-2 text-xs">
                  {dataReadiness.data.data_quality.gates_checklist.map((g) => (
                    <li key={g.id}>
                      <span className={g.passed ? 'text-emerald-700 dark:text-emerald-300' : ''}>
                        {g.passed ? '✓ ' : '○ '}
                      </span>
                      {g.label}: {g.current}/{g.threshold}
                    </li>
                  ))}
                </ul>
              ) : null}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-1 w-fit"
                onClick={() => {
                  requestAnimationFrame(() =>
                    document
                      .getElementById('batch-bulk-data-stage')
                      ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
                  );
                }}
              >
                {ru.batch.dataStageGoToUpload}
              </Button>
            </div>
          )}

          <div className="space-y-10">
            <section id="batch-evidence-dashboard" className="scroll-mt-24 space-y-3">
          <Separator />

          <Card className="shadow-sm">
            <CardHeader>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <CardTitle>{ru.batch.primaryEvidenceTitle}</CardTitle>
                  <CardDescription>
                    {dashboard.data?.batch
                      ? `${ru.batch.sourceCountLabel}: ${String(dashboard.data.batch.source_count ?? 0)}`
                      : null}
                  </CardDescription>
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">
                      {ru.batch.groupByLabel}
                    </label>
                    <select
                      className="flex h-9 min-w-[200px] rounded-md border border-input bg-background px-2 text-sm"
                      value={dashGroupBy}
                      onChange={(e) => setDashGroupBy(e.target.value)}
                    >
                      {GROUP_BY_OPTS.map((o) => (
                        <option key={o.value || 'all'} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-9"
                    disabled={dashboard.isFetching || dataReadiness.isFetching}
                    onClick={() => onRefreshDashboard()}
                  >
                    {ru.batch.refreshDashboard}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-9"
                    disabled={!dashboard.data}
                    onClick={() => void downloadBatchDashboardCsv(batchId, dashQueryOpts)}
                  >
                    {ru.batch.exportDashboardCsv}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-9"
                    disabled={!dashboard.data}
                    onClick={() => void downloadBatchDashboardPack(batchId, dashQueryOpts)}
                  >
                    {ru.batch.dashboardPackZip}
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-3 border-t pt-3 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-muted-foreground">{ru.batch.filterSegment}</label>
                  <select
                    className="flex h-9 min-w-[160px] rounded-md border border-input bg-background px-2 text-sm"
                    value={dashSegmentKey}
                    onChange={(e) => setDashSegmentKey(e.target.value)}
                    disabled={!dashGroupBy}
                  >
                    <option value="">{ru.batch.portraitSegmentAll}</option>
                    {(dashboard.data?.segment_breakdown ?? []).map((s) => (
                      <option key={s.segment_key} value={s.segment_key}>
                        {s.segment_key}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="font-medium text-muted-foreground">{ru.batch.filterDateFrom}</label>
                  <Input
                    type="date"
                    className="h-9 w-[150px] text-sm"
                    value={dashDateFrom}
                    onChange={(e) => setDashDateFrom(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="font-medium text-muted-foreground">{ru.batch.filterDateTo}</label>
                  <Input
                    type="date"
                    className="h-9 w-[150px] text-sm"
                    value={dashDateTo}
                    onChange={(e) => setDashDateTo(e.target.value)}
                  />
                </div>
                <label className="flex cursor-pointer items-center gap-2 pt-5">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    checked={dashStopwords}
                    onChange={(e) => setDashStopwords(e.target.checked)}
                  />
                  <span>{ru.batch.stopwordsMode}</span>
                </label>
              </div>
            </CardHeader>
            <CardContent className="space-y-8">
              {hasBatchSources ? (
                <BatchProcessingProgressSection
                  hasBatchSources={hasBatchSources}
                  audioPending={audioPipelineQuery.isPending}
                  audioError={audioPipelineQuery.error}
                  summary={audioPipelineQuery.data?.summary}
                  audioItems={audioPipelineQuery.data?.items ?? []}
                  diagnostics={
                    dashboard.data?.data_readiness_diagnostics ??
                    dataReadiness.data?.data_readiness_diagnostics
                  }
                  documentPipelines={
                    (dashboard.data?.document_pipelines ??
                      dataReadiness.data?.document_pipelines) as DocumentPipelineRow[] | undefined
                  }
                  batchSourceRows={batch.data?.sources}
                  queueActive={
                    !!batch.data?.queue_summary &&
                    ((batch.data.queue_summary.pending ?? 0) > 0 ||
                      (batch.data.queue_summary.processing ?? 0) > 0)
                  }
                  dashboardPending={dashboard.isPending}
                  refreshing={
                    dashboard.isFetching ||
                    dataReadiness.isFetching ||
                    audioPipelineQuery.isFetching ||
                    batch.isFetching
                  }
                  onRefreshNow={onRefreshProcessing}
                />
              ) : null}
              {dashboard.isPending && <Skeleton className="h-40 w-full" />}
              {dashboard.error && <ApiErrorText error={dashboard.error} />}
              {dashboard.data && (
                <>
                  {dashboard.data.data_readiness_diagnostics ? (
                    <div className="rounded-lg border border-primary/25 bg-primary/5 p-4 space-y-3">
                      <h3 className="text-sm font-semibold tracking-tight">{ru.batch.dataReadinessTitle}</h3>
                      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-xs">
                        <div>
                          <dt className="text-muted-foreground">{ru.batch.drInterviewsTotal}</dt>
                          <dd className="text-lg font-semibold tabular-nums">
                            {dashboard.data.data_readiness_diagnostics.interviews_total}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">{ru.batch.drInterviewsProcessed}</dt>
                          <dd className="text-lg font-semibold tabular-nums">
                            {dashboard.data.data_readiness_diagnostics.interviews_processed}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">{ru.batch.drChunksTotal}</dt>
                          <dd className="text-lg font-semibold tabular-nums">
                            {dashboard.data.data_readiness_diagnostics.chunks_total}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">{ru.batch.drEntitiesTotal}</dt>
                          <dd className="text-lg font-semibold tabular-nums">
                            {dashboard.data.data_readiness_diagnostics.entities_total}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">{ru.batch.drQuotesTotal}</dt>
                          <dd className="text-lg font-semibold tabular-nums">
                            {dashboard.data.data_readiness_diagnostics.quotes_total}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">{ru.batch.drDocsReady}</dt>
                          <dd className="text-lg font-semibold tabular-nums">
                            {dashboard.data.data_readiness_diagnostics.documents_ready} /{' '}
                            {dashboard.data.data_readiness_diagnostics.transcripts_completed}{' '}
                            <span className="text-[10px] font-normal text-muted-foreground">
                              ({ru.batch.drDocsReadyHint})
                            </span>
                          </dd>
                        </div>
                      </dl>
                      {(dashboard.data.data_readiness_diagnostics.missing_steps ?? []).length > 0 ? (
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">{ru.batch.drMissingSteps}</p>
                          <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-amber-900/90 dark:text-amber-100/85">
                            {(dashboard.data.data_readiness_diagnostics.missing_steps ?? []).map((s) => (
                              <li key={s}>
                                {(ru.batch.missingStepsMap as Record<string, string>)[s] ?? s}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {dashboard.data.data_readiness_diagnostics.pipelines_still_running ? (
                        <p className="text-xs text-muted-foreground">{ru.batch.drPipelineRunning}</p>
                      ) : null}
                    </div>
                  ) : null}
                  <p className="text-sm text-muted-foreground">{ru.batch.dataFirstDashboardHint}</p>
                  {dashboard.data.data_quality ? (
                    <DataQualityCallout
                      canSynthesize={
                        typeof dashboard.data.data_quality.strict_pr_ready === 'boolean'
                          ? dashboard.data.data_quality.strict_pr_ready
                          : dashboard.data.data_quality.can_synthesize_llm
                      }
                      warnings={dashboard.data.data_quality.warnings}
                      title={ru.batch.dataQualityBlock}
                    >
                      {dashboard.data.data_quality.gates_checklist &&
                      dashboard.data.data_quality.gates_checklist.length > 0 ? (
                        <div className="space-y-1">
                          <p className="text-xs font-medium text-muted-foreground">
                            {ru.batch.gatesChecklistTitle}
                          </p>
                          <ul className="list-none space-y-1 text-xs">
                            {dashboard.data.data_quality.gates_checklist.map((g) => (
                              <li
                                key={g.id}
                                className={cn(
                                  'rounded border px-2 py-1',
                                  g.passed ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-amber-500/30',
                                )}
                              >
                                <span className="font-medium">{g.label}</span>
                                {' — '}
                                <span className="text-muted-foreground">
                                  {g.current} / {g.threshold}
                                </span>
                                {g.passed ? (
                                  <span className="ml-1 text-emerald-700 dark:text-emerald-300">✓</span>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </DataQualityCallout>
                  ) : null}
                  {dashboard.data.audience_snapshot &&
                    typeof dashboard.data.audience_snapshot === 'object' && (
                      <div>
                        <h3 className="mb-2 text-sm font-semibold">{ru.batch.audienceTitle}</h3>
                        <p className="text-sm text-muted-foreground">
                          {ru.batch.interviewCount}:{' '}
                          {String(
                            (dashboard.data.audience_snapshot as { interview_count?: number })
                              .interview_count ?? 0,
                          )}
                        </p>
                      </div>
                    )}

                  {dashboard.data.evidence_dashboard &&
                  typeof dashboard.data.evidence_dashboard === 'object' ? (
                    <div className="rounded-lg border bg-muted/10 p-4 space-y-3">
                      <h3 className="text-sm font-semibold">{ru.batch.evidenceConsoleTitle}</h3>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
                        {(() => {
                          const kpis = (dashboard.data.evidence_dashboard as { kpis?: Record<string, unknown> })
                            .kpis;
                          if (!kpis) return null;
                          return (
                            <>
                              <div>
                                <p className="text-muted-foreground">{ru.batch.interviewCount}</p>
                                <p className="text-lg font-semibold">{String(kpis.interview_count ?? '—')}</p>
                              </div>
                              <div>
                                <p className="text-muted-foreground">{ru.batch.evidenceKpiEntities}</p>
                                <p className="text-lg font-semibold">{String(kpis.entity_rows ?? '—')}</p>
                              </div>
                              <div>
                                <p className="text-muted-foreground">{ru.batch.evidenceKpiQuotes}</p>
                                <p className="text-lg font-semibold">{String(kpis.evidence_quotes ?? '—')}</p>
                              </div>
                              <div>
                                <p className="text-muted-foreground">{ru.batch.dataCoverageLabel}</p>
                                <p className="text-lg font-semibold">
                                  {typeof kpis.data_coverage_score === 'number'
                                    ? `${Math.round((kpis.data_coverage_score as number) * 100)}%`
                                    : '—'}
                                </p>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {String(
                          (dashboard.data.evidence_dashboard as { kpis?: { extraction_quality_note?: string } })
                            .kpis?.extraction_quality_note ?? '',
                        )}
                      </p>
                      <div className="flex flex-wrap gap-3 items-end">
                        <div>
                          <p className="mb-1 text-xs text-muted-foreground">{ru.batch.chartSnapshotTopics}</p>
                          <img
                            src={batchChartSvgUrl(batchId, 'topics', dashQueryOpts)}
                            alt=""
                            className="max-h-40 rounded border bg-white"
                          />
                        </div>
                        <div>
                          <p className="mb-1 text-xs text-muted-foreground">{ru.batch.chartSnapshotProblems}</p>
                          <img
                            src={batchChartSvgUrl(batchId, 'problems', dashQueryOpts)}
                            alt=""
                            className="max-h-40 rounded border bg-white"
                          />
                        </div>
                      </div>
                    </div>
                  ) : null}

                  <BatchDashboardResearchWidgets
                    evidenceDashboard={
                      dashboard.data.evidence_dashboard &&
                      typeof dashboard.data.evidence_dashboard === 'object'
                        ? (dashboard.data.evidence_dashboard as Record<string, unknown>)
                        : undefined
                    }
                    fallbackWordFreq={dashboard.data.word_frequency}
                    fallbackPatterns={dashboard.data.top_patterns}
                    dashGroupBy={dashGroupBy}
                  />

                  <div>
                    <h3 className="mb-3 text-sm font-semibold">{ru.batch.sentiment}</h3>
                    <div className="flex flex-wrap gap-2 text-sm">
                      <Badge variant="secondary">
                        +: {dashboard.data.sentiment.positive_signals}
                        {typeof dashboard.data.sentiment.positive_pct === 'number'
                          ? ` (${dashboard.data.sentiment.positive_pct}%)`
                          : null}
                      </Badge>
                      <Badge variant="outline">
                        −: {dashboard.data.sentiment.negative_signals}
                        {typeof dashboard.data.sentiment.negative_pct === 'number'
                          ? ` (${dashboard.data.sentiment.negative_pct}%)`
                          : null}
                      </Badge>
                      {typeof dashboard.data.sentiment.neutralish_pct === 'number' ? (
                        <Badge variant="outline" className="font-normal text-muted-foreground">
                          ≈ {dashboard.data.sentiment.neutralish_pct}%
                        </Badge>
                      ) : null}
                      <Badge>{dashboard.data.sentiment.balance}</Badge>
                    </div>
                  </div>

                  {dashboard.data.evidence_dashboard &&
                  typeof dashboard.data.evidence_dashboard === 'object' ? (
                    (() => {
                      const ed = dashboard.data.evidence_dashboard as Record<string, unknown>;
                      const tl = (ed.timeline_series_real ?? ed.timeline) as
                        | {
                            series?: Array<{
                              period?: string;
                              sentiment_score?: number;
                              risk_index?: number;
                              theme_volume?: number;
                            }>;
                            emerging?: string[];
                            fading?: string[];
                            note?: string;
                          }
                        | undefined;
                      const series = Array.isArray(tl?.series)
                        ? tl!.series!.filter((x) => x && typeof x.period === 'string')
                        : [];
                      const emerging = Array.isArray(tl?.emerging) ? tl!.emerging! : [];
                      const fading = Array.isArray(tl?.fading) ? tl!.fading! : [];
                      const note = typeof tl?.note === 'string' ? tl.note : '';
                      return (
                        <div className="rounded-lg border bg-muted/10 p-4 space-y-3">
                          <h3 className="text-sm font-semibold">{ru.batch.trendDashboardTitle}</h3>
                          <p className="text-xs text-muted-foreground">{ru.batch.trendDashboardHint}</p>
                          {series.length === 0 ? (
                            <div className="flex min-h-[120px] flex-col justify-center rounded-md border border-dashed bg-background/40 p-4 text-center text-sm text-muted-foreground">
                              <p className="font-medium text-foreground/85">{ru.batch.trendEmptyTitle}</p>
                              <p className="mt-2 text-xs leading-relaxed">{note || ru.batch.trendEmptyBody}</p>
                            </div>
                          ) : (
                            <div className="space-y-4 text-xs">
                              <div className="overflow-x-auto">
                                <table className="w-full min-w-[320px] border-collapse text-left">
                                  <thead>
                                    <tr className="border-b text-muted-foreground">
                                      <th className="py-1 pr-2 font-medium">{ru.batch.trendPeriod}</th>
                                      <th className="py-1 pr-2 font-medium">{ru.batch.trendSentimentScore}</th>
                                      <th className="py-1 pr-2 font-medium">{ru.batch.trendRiskIndex}</th>
                                      <th className="py-1 font-medium">{ru.batch.trendThemeVolume}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {series.map((row, i) => (
                                      <tr key={i} className="border-b border-border/60">
                                        <td className="py-1.5 pr-2 font-mono text-[11px]">{row.period}</td>
                                        <td className="py-1.5 pr-2 tabular-nums">{row.sentiment_score ?? '—'}</td>
                                        <td className="py-1.5 pr-2 tabular-nums">{row.risk_index ?? '—'}</td>
                                        <td className="py-1.5 tabular-nums">{row.theme_volume ?? '—'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              {(emerging.length > 0 || fading.length > 0) && (
                                <div className="grid gap-3 sm:grid-cols-2">
                                  <div>
                                    <p className="mb-1 text-[11px] font-medium text-muted-foreground">
                                      {ru.batch.trendEmerging}
                                    </p>
                                    <ul className="list-disc space-y-0.5 pl-4">
                                      {emerging.slice(0, 8).map((t, j) => (
                                        <li key={j}>{t}</li>
                                      ))}
                                    </ul>
                                  </div>
                                  <div>
                                    <p className="mb-1 text-[11px] font-medium text-muted-foreground">
                                      {ru.batch.trendFading}
                                    </p>
                                    <ul className="list-disc space-y-0.5 pl-4">
                                      {fading.slice(0, 8).map((t, j) => (
                                        <li key={j}>{t}</li>
                                      ))}
                                    </ul>
                                  </div>
                                </div>
                              )}
                              {note ? <p className="text-[11px] text-muted-foreground">{note}</p> : null}
                            </div>
                          )}
                        </div>
                      );
                    })()
                  ) : null}

                  <div>
                    <h3 className="mb-3 text-sm font-semibold">{ru.batch.topicsPie}</h3>
                    {dashboard.data.topics_pie.length === 0 ? (
                      <div className="flex min-h-[100px] flex-col justify-center rounded-md border border-dashed bg-muted/15 p-4 text-center text-sm text-muted-foreground">
                        <p className="font-medium text-foreground/80">{ru.batch.chartSectionEmptyTitle}</p>
                        <p className="mt-1 text-xs leading-relaxed">
                          {dashboard.data.data_readiness_diagnostics?.visualization_note?.trim() ||
                            ru.batch.chartEmptyEntities}
                        </p>
                      </div>
                    ) : (
                      <ul className="space-y-2">
                        {dashboard.data.topics_pie.map((t, i) => (
                          <li key={i} className="flex items-center gap-2 text-sm">
                            <span
                              className="size-3 shrink-0 rounded-full bg-primary/70"
                              style={{ opacity: 0.35 + (0.65 * t.value) / topicTotal }}
                            />
                            <span className="flex-1">{t.label}</span>
                            <span className="text-muted-foreground tabular-nums">
                              {t.value}
                              {typeof t.pct === 'number' ? ` (${t.pct}%)` : ''}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div>
                    <h3 className="mb-3 text-sm font-semibold">{ru.batch.problemsBar}</h3>
                    {dashboard.data.problems_bar.length === 0 ? (
                      <div className="flex min-h-[100px] flex-col justify-center rounded-md border border-dashed bg-muted/15 p-4 text-center text-sm text-muted-foreground">
                        <p className="font-medium text-foreground/80">{ru.batch.chartSectionEmptyTitle}</p>
                        <p className="mt-1 text-xs leading-relaxed">
                          {dashboard.data.data_readiness_diagnostics?.visualization_note?.trim() ||
                            ru.batch.chartEmptyEntities}
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {dashboard.data.problems_bar.map((p, i) => (
                          <div key={i} className="flex items-center gap-2 text-sm">
                            <div className="h-2 w-24 shrink-0 overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full bg-destructive/70"
                                style={{ width: `${Math.round((100 * p.value) / maxProblem)}%` }}
                              />
                            </div>
                            <span className="min-w-0 flex-1 truncate">{p.label}</span>
                            <span className="text-muted-foreground tabular-nums">
                              {p.value}
                              {typeof p.pct === 'number' ? ` (${p.pct}%)` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="mb-3 text-sm font-semibold">{ru.batch.risksBar}</h3>
                    {(dashboard.data.risks_bar ?? []).length === 0 ? (
                      <div className="flex min-h-[100px] flex-col justify-center rounded-md border border-dashed bg-muted/15 p-4 text-center text-sm text-muted-foreground">
                        <p className="font-medium text-foreground/80">{ru.batch.chartSectionEmptyTitle}</p>
                        <p className="mt-1 text-xs leading-relaxed">
                          {dashboard.data.data_readiness_diagnostics?.visualization_note?.trim() ||
                            ru.batch.chartEmptyEntities}
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {(dashboard.data.risks_bar ?? []).map((p, i) => (
                          <div key={i} className="flex items-center gap-2 text-sm">
                            <div className="h-2 w-24 shrink-0 overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full bg-amber-600/70"
                                style={{ width: `${Math.round((100 * p.value) / maxRisk)}%` }}
                              />
                            </div>
                            <span className="min-w-0 flex-1 truncate">{p.label}</span>
                            <span className="text-muted-foreground tabular-nums">
                              {p.value}
                              {typeof p.pct === 'number' ? ` (${p.pct}%)` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="mb-3 text-sm font-semibold">{ru.batch.topInsights}</h3>
                    {dashboard.data.top_insights.length === 0 ? (
                      <div className="flex min-h-[80px] flex-col justify-center rounded-md border border-dashed bg-muted/15 p-4 text-center text-sm text-muted-foreground">
                        <p className="font-medium text-foreground/80">{ru.batch.chartSectionEmptyTitle}</p>
                        <p className="mt-1 text-xs leading-relaxed">
                          {dashboard.data.data_readiness_diagnostics?.visualization_note?.trim() ||
                            ru.batch.chartEmptyEntities}
                        </p>
                      </div>
                    ) : (
                      <ul className="space-y-2 text-sm">
                        {dashboard.data.top_insights.map((x, i) => (
                          <li key={i} className="rounded-md border bg-muted/20 p-3">
                            <Badge variant="secondary" className="mb-1">
                              {x.pr_signal_type || x.type || '—'}
                            </Badge>
                            <p className="leading-relaxed">{x.text}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <TracedTraceability traced={dashboard.data.traced} />

                  {dashGroupBy && (dashboard.data.segment_breakdown?.length ?? 0) > 0 && (
                    <div className="space-y-6 border-t pt-6">
                      <h3 className="text-sm font-semibold">{ru.batch.segmentBreakdown}</h3>
                      {dashboard.data.segment_breakdown.map((seg) => (
                        <div key={seg.segment_key} className="rounded-lg border bg-muted/10 p-4">
                          <p className="mb-2 font-medium">
                            {seg.segment_key}{' '}
                            <span className="text-muted-foreground">
                              ({seg.entity_count} {ru.batch.entitiesLabel})
                            </span>
                          </p>
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                                {ru.batch.topicsPie}
                              </h4>
                              <ul className="text-xs">
                                {seg.topics_pie.slice(0, 6).map((t, i) => (
                                  <li key={i}>
                                    {t.label}: {t.value}
                                    {typeof t.pct === 'number' ? ` (${t.pct}%)` : ''}
                                  </li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                                {ru.batch.problemsBar}
                              </h4>
                              <ul className="text-xs">
                                {seg.problems_bar.slice(0, 6).map((t, i) => (
                                  <li key={i}>
                                    {t.label}: {t.value}
                                    {typeof t.pct === 'number' ? ` (${t.pct}%)` : ''}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
            </section>

            <section id="batch-action-console" className="scroll-mt-24 space-y-4">
              <h2 className="text-lg font-semibold tracking-tight text-foreground">
                {ru.batch.primaryActionTitle}
              </h2>
              {!aiPipelineBlocksFeatures && prStrategyQuery.data ? (
                <div className="space-y-6">
                  {(prStrategyQuery.data.action_cards?.length ?? 0) > 0 ? (
                    <Card className="shadow-sm border-primary/20">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{ru.batch.actionConsoleTitle}</CardTitle>
                        <CardDescription>{ru.batch.actionConsoleHint}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {(prStrategyQuery.data.action_cards ?? []).map((c, idx) => (
                          <div
                            key={idx}
                            className="rounded-md border bg-muted/10 p-3 text-sm space-y-2"
                          >
                            <p className="font-medium text-foreground">{c.action || c.message}</p>
                            <p className="text-xs text-muted-foreground">
                              {c.channel ? `${ru.batch.actionCardChannel}: ${c.channel} · ` : null}
                              {c.for_segment ? `${ru.batch.actionCardSegment}: ${c.for_segment}` : null}
                            </p>
                            <p className="text-sm">{c.message}</p>
                            <p className="text-xs text-muted-foreground">
                              <span className="font-medium text-foreground/80">{ru.batch.actionCardEffect}: </span>
                              {c.expected_effect || '—'}
                            </p>
                            <p className="text-xs text-amber-900/85 dark:text-amber-100/85">
                              <span className="font-medium">{ru.batch.actionCardRisk}: </span>
                              {c.risk_if_ignored || '—'}
                            </p>
                            <p className="text-[10px] uppercase text-muted-foreground">
                              {c.evidence_status === 'ok' ? ru.batch.evidenceOk : ru.batch.evidenceInsufficient}
                            </p>
                            {(c.evidence_refs ?? []).length > 0 ? (
                              <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                                {(c.evidence_refs ?? []).map((e, j) => (
                                  <li key={j}>{(e.quote || '').slice(0, 400)}</li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  ) : null}
                  {(prStrategyQuery.data.pr_risk_alerts_v2?.length ?? 0) > 0 ? (
                    <Card className="shadow-sm border-amber-500/30">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{ru.batch.prRiskAlertsV2Title}</CardTitle>
                        <CardDescription>{ru.batch.prRiskAlertsV2Hint}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {(prStrategyQuery.data.pr_risk_alerts_v2 ?? []).map((a, i) => (
                          <div key={i} className="rounded-md border bg-muted/10 p-3 text-sm space-y-3">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="space-y-1">
                                <p className="font-medium leading-snug">{a.title}</p>
                                <div className="flex flex-wrap items-center gap-2">
                                  <Badge variant={a.severity === 'high' ? 'destructive' : 'secondary'}>
                                    {a.severity}
                                  </Badge>
                                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                    <PrRiskTrendIcon trend={a.trend} />
                                    {a.trend}
                                  </span>
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="text-[10px] font-medium uppercase text-muted-foreground">
                                  {ru.batch.riskIndexLabel}
                                </p>
                                <p className="text-2xl font-semibold tabular-nums">{a.risk_index}</p>
                              </div>
                            </div>
                            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full bg-amber-500/90"
                                style={{ width: `${Math.min(100, Math.max(0, a.risk_index))}%` }}
                              />
                            </div>
                            {(a.evidence_refs ?? []).slice(0, 4).length > 0 ? (
                              <ul className="space-y-2 border-t pt-2 text-xs">
                                {(a.evidence_refs ?? []).slice(0, 4).map((e, j) => {
                                  const href = evidenceRefHref(e);
                                  return (
                                    <li key={j} className="rounded-md border bg-background/60 p-2">
                                      <p className="text-muted-foreground leading-relaxed">
                                        {(e.quote || '').slice(0, 420)}
                                      </p>
                                      <div className="mt-2 flex flex-wrap items-center gap-2">
                                        {href ? (
                                          <Link
                                            to={href}
                                            className="text-[11px] font-medium text-primary underline-offset-2 hover:underline"
                                          >
                                            {ru.batch.openTracedSource}
                                          </Link>
                                        ) : (
                                          <span className="text-[10px] text-muted-foreground">
                                            {refLabelRefs({
                                              entity_id: e.entity_id ?? null,
                                              source_document_id: e.source_document_id ?? null,
                                              source_audio_id: e.source_audio_id ?? null,
                                              transcript_id: e.transcript_id ?? null,
                                            })}
                                          </span>
                                        )}
                                      </div>
                                    </li>
                                  );
                                })}
                              </ul>
                            ) : null}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  ) : null}
                  <div className="rounded-lg border bg-muted/15 p-4 space-y-3">
                    <div>
                      <h3 className="text-sm font-semibold">{ru.batch.decisionLayerSectionTitle}</h3>
                      <p className="text-xs text-muted-foreground">{ru.batch.decisionLayerSectionHint}</p>
                    </div>
                    <DecisionLayerPanel
                      priority_actions={prStrategyQuery.data.priority_actions}
                      impact_effort_matrix={prStrategyQuery.data.impact_effort_matrix}
                      alerts={prStrategyQuery.data.alerts}
                    />
                  </div>
                </div>
              ) : null}
            </section>

            <Collapsible defaultOpen={false} className="rounded-lg border bg-card/40 shadow-sm">
              <CollapsibleTrigger
                className={cn(
                  buttonVariants({ variant: 'ghost' }),
                  'flex h-12 w-full items-center justify-between gap-2 px-4 py-2 text-left font-medium hover:bg-muted/40',
                )}
              >
                <span>{ru.batch.advancedPanelTitle}</span>
                <ChevronDown className="size-4 shrink-0" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <p className="border-t px-4 pb-3 pt-2 text-xs text-muted-foreground">{ru.batch.advancedPanelHint}</p>
                <Tabs
                  value={advancedTab}
                  onValueChange={(v) => {
                    const t = v as
                      | 'overview'
                      | 'portrait'
                      | 'prstrategy'
                      | 'fullreport'
                      | 'compare'
                      | 'scenarios'
                      | 'corpus';
                    if (strictPrBlocksAi) {
                      if (t === 'overview' || t === 'corpus') setAdvancedTab(t);
                      return;
                    }
                    setAdvancedTab(t);
                  }}
                  className="space-y-6 px-2 pb-4"
                >
                  <TabsList
                    variant="line"
                    className="h-auto min-h-10 w-full flex-wrap justify-start gap-1"
                  >
                    <TabsTrigger value="overview">{ru.batch.tabSources}</TabsTrigger>
                    <TabsTrigger value="portrait" disabled={strictPrBlocksAi}>
                      {ru.batch.tabPortrait}
                    </TabsTrigger>
                    <TabsTrigger value="prstrategy" disabled={strictPrBlocksAi}>
                      {ru.batch.tabPrStrategy}
                    </TabsTrigger>
                    <TabsTrigger value="fullreport" disabled={strictPrBlocksAi}>
                      {ru.batch.tabFullReport}
                    </TabsTrigger>
                    <TabsTrigger value="compare" disabled={strictPrBlocksAi}>
                      {ru.batch.tabCompare}
                    </TabsTrigger>
                    <TabsTrigger value="scenarios" disabled={strictPrBlocksAi}>
                      {ru.batch.tabScenarios}
                    </TabsTrigger>
                    <TabsTrigger value="corpus">{ru.batch.tabCorpus}</TabsTrigger>
                  </TabsList>

            <TabsContent value="overview" className="mt-0 space-y-8">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>{ru.batch.sourcesInBatch}</CardTitle>
              <CardDescription>
                {batchDocumentSources.length === 0 ? ru.batch.noDocumentSources : null}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {batchDocumentSources.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{ru.project.tableType}</TableHead>
                      <TableHead>{ru.project.tableName}</TableHead>
                      <TableHead>{ru.batch.metadataColumn}</TableHead>
                      <TableHead className="w-[120px]">{ru.project.tableActions}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {batchDocumentSources.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell>{ru.batch.kindDocument}</TableCell>
                        <TableCell className="max-w-[200px] truncate font-mono text-xs">
                          {s.filename || s.source_document_id}
                        </TableCell>
                        <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                          {metaPreview(s.metadata_json)}
                        </TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={removeMut.isPending}
                            onClick={() => removeMut.mutate(s.id)}
                          >
                            {ru.batch.removeSource}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : null}
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>{ru.batch.interviewUnitsCard}</CardTitle>
              <CardDescription>{ru.batch.interviewUnitsCardDesc}</CardDescription>
            </CardHeader>
            <CardContent>
              {interviewUnits.isPending && <Skeleton className="h-24 w-full" />}
              {interviewUnits.error && <ApiErrorText error={interviewUnits.error} />}
              {!interviewUnits.isPending &&
                !(interviewUnits.data?.items?.length) &&
                hasInterviewSources && (
                  <p className="text-sm text-muted-foreground">{ru.batch.interviewUnitsEmpty}</p>
                )}
              {!!interviewUnits.data?.items?.length && (
                <div className="max-h-[320px] overflow-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>#</TableHead>
                        <TableHead>ID</TableHead>
                        <TableHead>{ru.batch.metaLanguage}</TableHead>
                        <TableHead>conf</TableHead>
                        <TableHead>split</TableHead>
                        <TableHead>preview</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {interviewUnits.data.items.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell>{u.unit_index}</TableCell>
                          <TableCell className="max-w-[120px] truncate font-mono text-xs">{u.id}</TableCell>
                          <TableCell>{u.language ?? '—'}</TableCell>
                          <TableCell>
                            {typeof u.language_confidence === 'number'
                              ? `${Math.round(u.language_confidence * 100)}%`
                              : '—'}
                          </TableCell>
                          <TableCell className="text-xs">{u.split_method}</TableCell>
                          <TableCell className="max-w-md text-xs text-muted-foreground">
                            {u.text_preview}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {hasBatchAudio ? (
            <Card className="shadow-sm">
              <CardHeader>
                <CardTitle>{ru.batch.audioPipelineSummary}</CardTitle>
                <CardDescription className="space-y-1">
                  {audioPipelineQuery.data
                    ? ru.batch.audioPipelineLine(
                        audioPipelineQuery.data.summary.ready,
                        audioPipelineQuery.data.summary.total_audios,
                        audioPipelineQuery.data.summary.in_progress,
                      )
                    : null}
                  {audioPipelineQuery.data?.summary.failed
                    ? ` ${ru.batch.audioPipelineFailedFiles(audioPipelineQuery.data.summary.failed)}`
                    : null}
                  {audioPipelineQuery.data?.summary.total_interviews != null ? (
                    <span className="block text-xs text-muted-foreground">
                      {ru.batch.batchInterviewProgress(
                        audioPipelineQuery.data.summary.processed_interviews ?? 0,
                        audioPipelineQuery.data.summary.total_interviews ?? 0,
                        audioPipelineQuery.data.summary.errors_count ?? 0,
                      )}
                    </span>
                  ) : null}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {audioPipelineQuery.isPending && <Skeleton className="h-24 w-full" />}
                {audioPipelineQuery.error && <ApiErrorText error={audioPipelineQuery.error} />}
                {audioPipelineQuery.data &&
                  (audioPipelineQuery.data.items.length ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{ru.project.tableName}</TableHead>
                          <TableHead>{ru.batch.audioProgressCol}</TableHead>
                          <TableHead>{ru.pipeline.chunksLabel}</TableHead>
                          <TableHead>%</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {audioPipelineQuery.data.items.map((it) => {
                          const total = Math.max(0, it.total_chunks);
                          const done = Math.max(0, it.done_chunks);
                          const pct =
                            typeof it.progress_percent === 'number'
                              ? it.progress_percent
                              : total > 0
                                ? Math.min(100, Math.round((100 * done) / total))
                                : 0;
                          const stage = (it.pipeline_stage || it.current_stage || 'unknown').toString();
                          return (
                            <TableRow key={it.source_audio_id}>
                              <TableCell className="max-w-[220px] text-xs">
                                {it.filename || it.source_audio_id}
                              </TableCell>
                              <TableCell className="text-xs">
                                {ru.pipeline.audioStage(stage)}
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {ru.batch.audioPipelineChunksBatch(done, total, it.failed_chunks)}
                              </TableCell>
                              <TableCell className="tabular-nums text-xs">
                                {pct}%{it.last_error ? ` — ${it.last_error}` : ''}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  ) : (
                    <p className="text-sm text-muted-foreground">—</p>
                  ))}
              </CardContent>
            </Card>
          ) : null}

          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>{ru.batch.projectSources}</CardTitle>
              <CardDescription>{ru.batch.selectHint}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  disabled={selected.size === 0 || addSelectedMut.isPending}
                  onClick={() => addSelectedMut.mutate()}
                >
                  {addSelectedMut.isPending ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : null}
                  {ru.batch.addSelected}
                </Button>
              </div>
              {addSelectedMut.error && <ApiErrorText error={addSelectedMut.error} />}
              {sources.isPending && <Skeleton className="h-32 w-full" />}
              {sources.data && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10" />
                      <TableHead>{ru.project.tableType}</TableHead>
                      <TableHead>{ru.project.tableName}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.data.items
                      .filter((item) => item.source_kind === 'document')
                      .map((item) => {
                      const key = sourceKey(item);
                      const taken = inBatch.has(key);
                      return (
                        <TableRow key={key}>
                          <TableCell>
                            <input
                              type="checkbox"
                              className="size-4 accent-primary"
                              disabled={taken}
                              checked={selected.has(key)}
                              onChange={() => toggle(key)}
                              aria-label={key}
                            />
                          </TableCell>
                          <TableCell>
                            {item.source_kind === 'document'
                              ? ru.batch.kindDocument
                              : ru.batch.kindAudio}
                          </TableCell>
                          <TableCell>
                            {item.filename}
                            {taken ? (
                              <Badge variant="outline" className="ml-2">
                                {ru.batch.inStudyBadge}
                              </Badge>
                            ) : null}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
            </TabsContent>

            <TabsContent value="portrait" className="mt-0 space-y-6">
              {processingPipelineIncomplete && !strictPrBlocksAi ? (
                <BatchAiProcessingGateCard />
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">{ru.batch.portraitIntro}</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">{ru.batch.groupByLabel}</label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={portraitGroupBy}
                    onChange={(e) => setPortraitGroupBy(e.target.value)}
                  >
                    {GROUP_BY_OPTS.map((o) => (
                      <option key={o.value || 'all'} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">{ru.batch.portraitSegmentLabel}</label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={portraitSegment}
                    onChange={(e) => setPortraitSegment(e.target.value)}
                    disabled={!portraitGroupBy}
                  >
                    <option value="">{ru.batch.portraitSegmentAll}</option>
                    {(portraitSegmentsDash.data?.segment_breakdown ?? []).map((s) => (
                      <option key={s.segment_key} value={s.segment_key}>
                        {s.segment_key} ({s.entity_count})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              {!hasInterviewSources ? (
                <p className="text-sm text-muted-foreground">{ru.batch.noSources}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={portraitRecalc.isPending || aiPipelineBlocksFeatures}
                    onClick={() => portraitRecalc.mutate()}
                  >
                    {portraitRecalc.isPending ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : null}
                    {ru.batch.recalculateAi}
                  </Button>
                  {portraitQuery.isFetching && !portraitQuery.isPending ? (
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" />
                      {ru.batch.loadingAnalysis}
                    </span>
                  ) : null}
                </div>
              )}
              {portraitQuery.error && <ApiErrorText error={portraitQuery.error} />}
              {portraitRecalc.error && <ApiErrorText error={portraitRecalc.error} />}
              {portraitQuery.isPending && hasInterviewSources && (
                <div className="space-y-3">
                  <Skeleton className="h-24 w-full" />
                  <Skeleton className="h-24 w-full" />
                  <Skeleton className="h-24 w-full" />
                </div>
              )}
              {portraitQuery.data && (
                <div className="space-y-4">
                  <SynthesisTextBanner
                    message={portraitQuery.data.data_quality_message}
                    blocked={portraitQuery.data.synthesis_blocked}
                  />
                  <DataQualityCallout
                    canSynthesize={!portraitQuery.data.synthesis_blocked}
                    warnings={portraitQuery.data.data_quality_warnings ?? []}
                  />
                  <AnalysisStatsLine
                    confidence={portraitQuery.data.confidence}
                    dataCoverageScore={portraitQuery.data.data_coverage_score}
                    interviewCount={portraitQuery.data.interview_count}
                    distribution={portraitQuery.data.segment_distribution}
                    metaInterviewCount={
                      (portraitQuery.data.meta as { interview_count?: number }).interview_count
                    }
                  />
                  <SampleQuotesList items={portraitQuery.data.sample_quotes ?? []} />
                  {(
                    [
                      ['decision_making', ru.batch.portraitDecision],
                      ['fears', ru.batch.portraitFears],
                      ['trust_drivers', ru.batch.portraitTrust],
                      ['pain_points', ru.batch.portraitPain],
                      ['language_style', ru.batch.portraitLanguage],
                      ['brand_perception', ru.batch.portraitBrand],
                      ['emotional_triggers', ru.batch.portraitEmotional],
                    ] as const
                  ).map(([key, label]) => {
                    const fk = key as PortraitFieldKey;
                    return (
                    <Card key={key} className="shadow-sm">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{label}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                          {portraitQuery.data.portrait[key]}
                        </p>
                        <FieldGroundingList
                          items={portraitQuery.data.portrait_grounding?.[fk] ?? null}
                        />
                      </CardContent>
                    </Card>
                  );
                  })}
                </div>
              )}
                </>
              )}
            </TabsContent>

            <TabsContent value="prstrategy" className="mt-0 space-y-6">
              {processingPipelineIncomplete && !strictPrBlocksAi ? (
                <BatchAiProcessingGateCard />
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">{ru.batch.prStrategyIntro}</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">{ru.batch.groupByLabel}</label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={portraitGroupBy}
                    onChange={(e) => setPortraitGroupBy(e.target.value)}
                  >
                    {GROUP_BY_OPTS.map((o) => (
                      <option key={o.value || 'all'} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">{ru.batch.portraitSegmentLabel}</label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={portraitSegment}
                    onChange={(e) => setPortraitSegment(e.target.value)}
                    disabled={!portraitGroupBy}
                  >
                    <option value="">{ru.batch.portraitSegmentAll}</option>
                    {(portraitSegmentsDash.data?.segment_breakdown ?? []).map((s) => (
                      <option key={s.segment_key} value={s.segment_key}>
                        {s.segment_key} ({s.entity_count})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              {!hasInterviewSources ? (
                <p className="text-sm text-muted-foreground">{ru.batch.noSources}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={prStrategyRecalc.isPending || aiPipelineBlocksFeatures}
                    onClick={() => prStrategyRecalc.mutate()}
                  >
                    {prStrategyRecalc.isPending ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : null}
                    {ru.batch.recalculateAi}
                  </Button>
                  {prStrategyQuery.isFetching && !prStrategyQuery.isPending ? (
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" />
                      {ru.batch.loadingAnalysis}
                    </span>
                  ) : null}
                </div>
              )}
              {prStrategyQuery.error && <ApiErrorText error={prStrategyQuery.error} />}
              {prStrategyRecalc.error && <ApiErrorText error={prStrategyRecalc.error} />}
              {prStrategyQuery.isPending && hasInterviewSources && (
                <div className="space-y-3">
                  <Skeleton className="h-28 w-full" />
                  <Skeleton className="h-28 w-full" />
                </div>
              )}
              {prStrategyQuery.data && (
                <div className="space-y-6">
                  <SynthesisTextBanner
                    message={prStrategyQuery.data.data_quality_message}
                    blocked={prStrategyQuery.data.synthesis_blocked}
                  />
                  <DataQualityCallout
                    canSynthesize={!prStrategyQuery.data.synthesis_blocked}
                    warnings={prStrategyQuery.data.data_quality_warnings ?? []}
                  />
                  <AnalysisStatsLine
                    confidence={prStrategyQuery.data.confidence}
                    dataCoverageScore={prStrategyQuery.data.data_coverage_score}
                    interviewCount={prStrategyQuery.data.interview_count}
                    distribution={prStrategyQuery.data.segment_distribution}
                    metaInterviewCount={
                      (prStrategyQuery.data.meta as { interview_count?: number }).interview_count
                    }
                  />
                  <SampleQuotesList items={prStrategyQuery.data.sample_quotes ?? []} />
                  {(prStrategyQuery.data.action_cards?.length ?? 0) > 0 ? (
                    <Card className="shadow-sm border-primary/20">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{ru.batch.actionConsoleTitle}</CardTitle>
                        <CardDescription>{ru.batch.actionConsoleHint}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {(prStrategyQuery.data.action_cards ?? []).map((c, idx) => (
                          <div
                            key={idx}
                            className="rounded-md border bg-muted/10 p-3 text-sm space-y-2"
                          >
                            <p className="font-medium text-foreground">{c.action || c.message}</p>
                            <p className="text-xs text-muted-foreground">
                              {c.channel ? `${ru.batch.actionCardChannel}: ${c.channel} · ` : null}
                              {c.for_segment ? `${ru.batch.actionCardSegment}: ${c.for_segment}` : null}
                            </p>
                            <p className="text-sm">{c.message}</p>
                            <p className="text-xs text-muted-foreground">
                              <span className="font-medium text-foreground/80">{ru.batch.actionCardEffect}: </span>
                              {c.expected_effect || '—'}
                            </p>
                            <p className="text-xs text-amber-900/85 dark:text-amber-100/85">
                              <span className="font-medium">{ru.batch.actionCardRisk}: </span>
                              {c.risk_if_ignored || '—'}
                            </p>
                            <p className="text-[10px] uppercase text-muted-foreground">
                              {c.evidence_status === 'ok' ? ru.batch.evidenceOk : ru.batch.evidenceInsufficient}
                            </p>
                            {(c.evidence_refs ?? []).length > 0 ? (
                              <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                                {(c.evidence_refs ?? []).map((e, j) => (
                                  <li key={j}>{(e.quote || '').slice(0, 400)}</li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  ) : null}
                  {!aiPipelineBlocksFeatures ? (
                    <Card className="shadow-sm">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{ru.batch.messageLabTitle}</CardTitle>
                        <CardDescription>{ru.batch.messageLabHint}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <Textarea
                          value={messageLabDraft}
                          onChange={(e) => setMessageLabDraft(e.target.value)}
                          placeholder={ru.batch.messageLabPlaceholder}
                          className="min-h-[88px] text-sm"
                        />
                        <Button
                          type="button"
                          size="sm"
                          disabled={messageLabMut.isPending || !messageLabDraft.trim()}
                          onClick={() => messageLabMut.mutate()}
                        >
                          {messageLabMut.isPending ? (
                            <Loader2 className="mr-2 size-4 animate-spin" />
                          ) : null}
                          {ru.batch.messageLabRun}
                        </Button>
                        {messageLabMut.error ? <ApiErrorText error={messageLabMut.error} /> : null}
                        {messageLabResult ? (
                          <div className="rounded-md border p-3 text-sm space-y-2">
                            {messageLabResult.insufficient_evidence ? (
                              <p className="text-amber-900/90 dark:text-amber-100/85">
                                {messageLabResult.notes || ru.batch.evidenceInsufficient}
                              </p>
                            ) : (
                              <>
                                <p className="text-xs text-muted-foreground">
                                  clarity {Math.round((messageLabResult.clarity_score ?? 0) * 100)}% · trust{' '}
                                  {Math.round((messageLabResult.trust_score ?? 0) * 100)}% · risk{' '}
                                  {Math.round((messageLabResult.risk_score ?? 0) * 100)}%
                                </p>
                                {(messageLabResult.rewrite_variants ?? []).map((r, i) => (
                                  <p key={i} className="whitespace-pre-wrap text-sm">
                                    <span className="font-medium">
                                      {i === 0 ? ru.batch.messageLabRewrite1 : ru.batch.messageLabRewrite2}
                                    </span>
                                    {r}
                                  </p>
                                ))}
                                {(messageLabResult.segment_reactions ?? []).map((s, i) => (
                                  <p key={i} className="text-xs text-muted-foreground">
                                    <span className="font-medium text-foreground/80">{s.segment}: </span>
                                    {s.reaction}
                                  </p>
                                ))}
                              </>
                            )}
                          </div>
                        ) : null}
                      </CardContent>
                    </Card>
                  ) : null}
                  {(prStrategyQuery.data.action_cards?.length ?? 0) > 0 ? (
                    (prStrategyQuery.data.brand_perception_summary || '').trim() ? (
                      <div className="rounded-md border border-primary/20 bg-muted/10 px-3 py-2 text-sm text-muted-foreground">
                        <span className="font-medium text-foreground">{ru.batch.prBrandSummary}: </span>
                        {prStrategyQuery.data.brand_perception_summary}
                      </div>
                    ) : null
                  ) : (
                    <>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prBrandSummary}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                            {prStrategyQuery.data.brand_perception_summary || '—'}
                          </p>
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prKeyInsights}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.key_pr_insights} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prRisks}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.reputational_risks} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prGaps}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.communication_gaps} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prMessages}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.recommended_messages} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prTalkingPoints}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.talking_points} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prMediaHooks}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.media_hooks} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prNextSteps}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={prStrategyQuery.data.next_steps} />
                        </CardContent>
                      </Card>
                      {prStrategyQuery.data.pr_grounding && prStrategyQuery.data.pr_grounding.length > 0 ? (
                        <Card className="shadow-sm">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">{ru.batch.prGroundingTitle}</CardTitle>
                          </CardHeader>
                          <CardContent className="space-y-3 text-xs">
                            {prStrategyQuery.data.pr_grounding.map((row, i) => (
                              <div key={i} className="rounded border bg-muted/10 p-2">
                                <p className="text-sm font-medium text-foreground">{row.insight}</p>
                                <p className="text-[10px] text-muted-foreground">{row.insight_kind}</p>
                                <ul className="mt-1 list-disc space-y-1 pl-4 text-muted-foreground">
                                  {row.evidence.map((e, j) => (
                                    <li key={j} className="whitespace-pre-wrap">
                                      {e.quote}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ))}
                          </CardContent>
                        </Card>
                      ) : null}
                    </>
                  )}
                  <DecisionLayerPanel
                    priority_actions={prStrategyQuery.data.priority_actions}
                    impact_effort_matrix={prStrategyQuery.data.impact_effort_matrix}
                    alerts={prStrategyQuery.data.alerts}
                  />
                </div>
              )}
                </>
              )}
            </TabsContent>

            <TabsContent value="fullreport" className="mt-0 space-y-6">
              {processingPipelineIncomplete && !strictPrBlocksAi ? (
                <BatchAiProcessingGateCard />
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">{ru.batch.fullReportIntro}</p>
              {!hasInterviewSources ? (
                <p className="text-sm text-muted-foreground">{ru.batch.noSources}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={fullReportRecalc.isPending || aiPipelineBlocksFeatures}
                    onClick={() => fullReportRecalc.mutate()}
                  >
                    {fullReportRecalc.isPending ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : null}
                    {ru.batch.recalculateAi}
                  </Button>
                  {fullReportQuery.isFetching && !fullReportQuery.isPending ? (
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" />
                      {ru.batch.loadingAnalysis}
                    </span>
                  ) : null}
                </div>
              )}
              {fullReportQuery.error && <ApiErrorText error={fullReportQuery.error} />}
              {fullReportRecalc.error && <ApiErrorText error={fullReportRecalc.error} />}
              {fullReportQuery.isPending && hasInterviewSources && (
                <div className="space-y-3">
                  <Skeleton className="h-32 w-full" />
                  <Skeleton className="h-32 w-full" />
                </div>
              )}
              {fullReportQuery.data && (
                <div className="space-y-6">
                  <AnalysisStatsLine
                    confidence={fullReportQuery.data.confidence}
                    interviewCount={fullReportQuery.data.interview_count}
                    distribution={fullReportQuery.data.segment_distribution}
                  />
                  <Card className="shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{ru.batch.executiveSummary}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                        {fullReportQuery.data.executive_summary || '—'}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{ru.batch.fullReportRisks}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <BulletList items={fullReportQuery.data.risks} />
                    </CardContent>
                  </Card>
                  <Card className="shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{ru.batch.fullReportRecommendations}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <BulletList items={fullReportQuery.data.recommendations} />
                    </CardContent>
                  </Card>
                  <Card className="shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{ru.batch.fullReportNextSteps}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <BulletList items={fullReportQuery.data.next_steps} />
                    </CardContent>
                  </Card>
                  <Separator />
                  <p className="text-sm font-medium text-foreground">{ru.batch.tabPortrait}</p>
                  <SynthesisTextBanner
                    message={fullReportQuery.data.audience_portrait.data_quality_message}
                    blocked={fullReportQuery.data.audience_portrait.synthesis_blocked}
                  />
                  <DataQualityCallout
                    canSynthesize={!fullReportQuery.data.audience_portrait.synthesis_blocked}
                    warnings={fullReportQuery.data.audience_portrait.data_quality_warnings ?? []}
                  />
                  <AnalysisStatsLine
                    confidence={fullReportQuery.data.audience_portrait.confidence}
                    dataCoverageScore={fullReportQuery.data.audience_portrait.data_coverage_score}
                    interviewCount={fullReportQuery.data.audience_portrait.interview_count}
                    distribution={fullReportQuery.data.audience_portrait.segment_distribution}
                    metaInterviewCount={
                      (
                        fullReportQuery.data.audience_portrait.meta as {
                          interview_count?: number;
                        }
                      ).interview_count
                    }
                  />
                  <SampleQuotesList items={fullReportQuery.data.audience_portrait.sample_quotes ?? []} />
                  {(
                    [
                      ['decision_making', ru.batch.portraitDecision],
                      ['fears', ru.batch.portraitFears],
                      ['trust_drivers', ru.batch.portraitTrust],
                      ['pain_points', ru.batch.portraitPain],
                      ['language_style', ru.batch.portraitLanguage],
                      ['brand_perception', ru.batch.portraitBrand],
                      ['emotional_triggers', ru.batch.portraitEmotional],
                    ] as const
                  ).map(([key, label]) => {
                    const fk = key as PortraitFieldKey;
                    return (
                    <Card key={key} className="shadow-sm">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{label}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                          {fullReportQuery.data.audience_portrait.portrait[key]}
                        </p>
                        <FieldGroundingList
                          items={
                            fullReportQuery.data.audience_portrait.portrait_grounding?.[fk] ?? null
                          }
                        />
                      </CardContent>
                    </Card>
                  );
                  })}
                  <Separator />
                  <p className="text-sm font-medium text-foreground">{ru.batch.tabPrStrategy}</p>
                  <SynthesisTextBanner
                    message={fullReportQuery.data.pr_strategy.data_quality_message}
                    blocked={fullReportQuery.data.pr_strategy.synthesis_blocked}
                  />
                  <DataQualityCallout
                    canSynthesize={!fullReportQuery.data.pr_strategy.synthesis_blocked}
                    warnings={fullReportQuery.data.pr_strategy.data_quality_warnings ?? []}
                  />
                  <AnalysisStatsLine
                    confidence={fullReportQuery.data.pr_strategy.confidence}
                    dataCoverageScore={fullReportQuery.data.pr_strategy.data_coverage_score}
                    interviewCount={fullReportQuery.data.pr_strategy.interview_count}
                    distribution={fullReportQuery.data.pr_strategy.segment_distribution}
                    metaInterviewCount={
                      (fullReportQuery.data.pr_strategy.meta as { interview_count?: number })
                        .interview_count
                    }
                  />
                  <SampleQuotesList items={fullReportQuery.data.pr_strategy.sample_quotes ?? []} />
                  {fullReportQuery.data.pr_strategy.insufficient_data ? (
                    <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm space-y-2">
                      <p className="font-medium text-foreground">
                        {fullReportQuery.data.pr_strategy.insufficient_data.message}
                      </p>
                      <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                        {(fullReportQuery.data.pr_strategy.insufficient_data.missing ?? []).map((m, i) => (
                          <li key={i}>{m}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {(fullReportQuery.data.pr_strategy.action_cards?.length ?? 0) > 0 ? (
                    <Card className="shadow-sm border-primary/20">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{ru.batch.actionConsoleTitle}</CardTitle>
                        <CardDescription>{ru.batch.actionConsoleHint}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {(fullReportQuery.data.pr_strategy.action_cards ?? []).map((c, idx) => (
                          <div
                            key={idx}
                            className="rounded-md border bg-muted/10 p-3 text-sm space-y-2"
                          >
                            <p className="font-medium text-foreground">{c.action || c.message}</p>
                            <p className="text-xs text-muted-foreground">
                              {c.channel ? `${ru.batch.actionCardChannel}: ${c.channel} · ` : null}
                              {c.for_segment ? `${ru.batch.actionCardSegment}: ${c.for_segment}` : null}
                            </p>
                            <p className="text-sm">{c.message}</p>
                            <p className="text-xs text-muted-foreground">
                              <span className="font-medium text-foreground/80">{ru.batch.actionCardEffect}: </span>
                              {c.expected_effect || '—'}
                            </p>
                            <p className="text-xs text-amber-900/85 dark:text-amber-100/85">
                              <span className="font-medium">{ru.batch.actionCardRisk}: </span>
                              {c.risk_if_ignored || '—'}
                            </p>
                            <p className="text-[10px] uppercase text-muted-foreground">
                              {c.evidence_status === 'ok' ? ru.batch.evidenceOk : ru.batch.evidenceInsufficient}
                            </p>
                            {(c.evidence_refs ?? []).length > 0 ? (
                              <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                                {(c.evidence_refs ?? []).map((e, j) => (
                                  <li key={j}>{(e.quote || '').slice(0, 400)}</li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  ) : null}
                  {(fullReportQuery.data.pr_strategy.pr_risk_alerts_v2?.length ?? 0) > 0 ? (
                    <Card className="shadow-sm border-amber-500/30">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{ru.batch.prRiskAlertsV2Title}</CardTitle>
                        <CardDescription>{ru.batch.prRiskAlertsV2Hint}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {(fullReportQuery.data.pr_strategy.pr_risk_alerts_v2 ?? []).map((a, i) => (
                          <div key={i} className="rounded-md border bg-muted/10 p-3 text-sm space-y-3">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="space-y-1">
                                <p className="font-medium leading-snug">{a.title}</p>
                                <div className="flex flex-wrap items-center gap-2">
                                  <Badge variant={a.severity === 'high' ? 'destructive' : 'secondary'}>
                                    {a.severity}
                                  </Badge>
                                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                    <PrRiskTrendIcon trend={a.trend} />
                                    {a.trend}
                                  </span>
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="text-[10px] font-medium uppercase text-muted-foreground">
                                  {ru.batch.riskIndexLabel}
                                </p>
                                <p className="text-2xl font-semibold tabular-nums">{a.risk_index}</p>
                              </div>
                            </div>
                            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full bg-amber-500/90"
                                style={{ width: `${Math.min(100, Math.max(0, a.risk_index))}%` }}
                              />
                            </div>
                            {(a.evidence_refs ?? []).slice(0, 4).length > 0 ? (
                              <ul className="space-y-2 border-t pt-2 text-xs">
                                {(a.evidence_refs ?? []).slice(0, 4).map((e, j) => {
                                  const href = evidenceRefHref(e);
                                  return (
                                    <li key={j} className="rounded-md border bg-background/60 p-2">
                                      <p className="text-muted-foreground leading-relaxed">
                                        {(e.quote || '').slice(0, 420)}
                                      </p>
                                      <div className="mt-2 flex flex-wrap items-center gap-2">
                                        {href ? (
                                          <Link
                                            to={href}
                                            className="text-[11px] font-medium text-primary underline-offset-2 hover:underline"
                                          >
                                            {ru.batch.openTracedSource}
                                          </Link>
                                        ) : (
                                          <span className="text-[10px] text-muted-foreground">
                                            {refLabelRefs({
                                              entity_id: e.entity_id ?? null,
                                              source_document_id: e.source_document_id ?? null,
                                              source_audio_id: e.source_audio_id ?? null,
                                              transcript_id: e.transcript_id ?? null,
                                            })}
                                          </span>
                                        )}
                                      </div>
                                    </li>
                                  );
                                })}
                              </ul>
                            ) : null}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  ) : null}
                  {(fullReportQuery.data.priority_actions?.length ?? 0) > 0 ||
                  (fullReportQuery.data.pr_strategy.action_cards?.length ?? 0) > 0 ? (
                    <DecisionLayerPanel
                      priority_actions={fullReportQuery.data.priority_actions}
                      impact_effort_matrix={fullReportQuery.data.impact_effort_matrix}
                      alerts={fullReportQuery.data.alerts}
                    />
                  ) : null}
                  {(fullReportQuery.data.pr_strategy.action_cards?.length ?? 0) > 0 ? (
                    (fullReportQuery.data.pr_strategy.brand_perception_summary || '').trim() ? (
                      <div className="rounded-md border border-primary/20 bg-muted/10 px-3 py-2 text-sm text-muted-foreground">
                        <span className="font-medium text-foreground">{ru.batch.prBrandSummary}: </span>
                        {fullReportQuery.data.pr_strategy.brand_perception_summary}
                      </div>
                    ) : null
                  ) : !fullReportQuery.data.pr_strategy.synthesis_blocked ? (
                    <>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prBrandSummary}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                            {fullReportQuery.data.pr_strategy.brand_perception_summary || '—'}
                          </p>
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prKeyInsights}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.key_pr_insights} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prRisks}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.reputational_risks} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prGaps}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.communication_gaps} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prMessages}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.recommended_messages} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prTalkingPoints}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.talking_points} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prMediaHooks}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.media_hooks} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prNextSteps}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={fullReportQuery.data.pr_strategy.next_steps} />
                        </CardContent>
                      </Card>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {fullReportQuery.data.pr_strategy.data_quality_message || '—'}
                    </p>
                  )}
                </div>
              )}
                </>
              )}
            </TabsContent>

            <TabsContent value="compare" className="mt-0 space-y-6">
              {processingPipelineIncomplete && !strictPrBlocksAi ? (
                <BatchAiProcessingGateCard />
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">{ru.batch.compareIntro}</p>
              {!hasInterviewSources ? (
                <p className="text-sm text-muted-foreground">{ru.batch.noSources}</p>
              ) : (
                <>
                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{ru.batch.compareGroupBy}</label>
                      <select
                        className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={compareGroupBy}
                        onChange={(e) => setCompareGroupBy(e.target.value)}
                      >
                        {COMPARE_GROUP_OPTS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{ru.batch.compareSegmentA}</label>
                      <select
                        className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={compareSegA}
                        onChange={(e) => setCompareSegA(e.target.value)}
                        disabled={!compareDash.data?.segment_breakdown?.length}
                      >
                        <option value="">—</option>
                        {(compareDash.data?.segment_breakdown ?? []).map((s) => (
                          <option key={s.segment_key} value={s.segment_key}>
                            {s.segment_key} ({s.entity_count})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{ru.batch.compareSegmentB}</label>
                      <select
                        className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={compareSegB}
                        onChange={(e) => setCompareSegB(e.target.value)}
                        disabled={!compareDash.data?.segment_breakdown?.length}
                      >
                        <option value="">—</option>
                        {(compareDash.data?.segment_breakdown ?? []).map((s) => (
                          <option key={`b-${s.segment_key}`} value={s.segment_key}>
                            {s.segment_key} ({s.entity_count})
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  {!compareReady && (
                    <p className="text-sm text-muted-foreground">{ru.batch.comparePickBoth}</p>
                  )}
                  {compareDash.isPending && (
                    <Skeleton className="h-10 w-full max-w-md" />
                  )}
                  {compareQuery.isPending && compareReady && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      {ru.batch.loadingAnalysis}
                    </div>
                  )}
                  {compareQuery.error && <ApiErrorText error={compareQuery.error} />}
                  {compareQuery.data && (
                    <div className="space-y-8">
                      <div className="grid gap-4 lg:grid-cols-2">
                        <Card className="shadow-sm">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">
                              {compareQuery.data.segment_a.segment_key}
                            </CardTitle>
                            <CardDescription>
                              {compareQuery.data.segment_a.interview_count}{' '}
                              {ru.batch.interviewCountShort}
                            </CardDescription>
                          </CardHeader>
                          <CardContent className="space-y-4 text-sm">
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareTopics}</p>
                              <FreqChips rows={compareQuery.data.segment_a.topic_frequency} />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareProblems}</p>
                              <FreqChips rows={compareQuery.data.segment_a.problem_frequency} />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareRisks}</p>
                              <FreqChips rows={compareQuery.data.segment_a.risk_frequency} />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareWords}</p>
                              <FreqChips
                                rows={(compareQuery.data.segment_a.word_frequency || []).map((w) => ({
                                  label: w.word,
                                  value: w.count,
                                }))}
                                limit={10}
                              />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.comparePortraitShort}</p>
                              <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                                {compareQuery.data.segment_a.audience_portrait_summary || '—'}
                              </p>
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.comparePrShort}</p>
                              <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                                {compareQuery.data.segment_a.pr_strategy_summary || '—'}
                              </p>
                            </div>
                          </CardContent>
                        </Card>
                        <Card className="shadow-sm">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">
                              {compareQuery.data.segment_b.segment_key}
                            </CardTitle>
                            <CardDescription>
                              {compareQuery.data.segment_b.interview_count}{' '}
                              {ru.batch.interviewCountShort}
                            </CardDescription>
                          </CardHeader>
                          <CardContent className="space-y-4 text-sm">
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareTopics}</p>
                              <FreqChips rows={compareQuery.data.segment_b.topic_frequency} />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareProblems}</p>
                              <FreqChips rows={compareQuery.data.segment_b.problem_frequency} />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareRisks}</p>
                              <FreqChips rows={compareQuery.data.segment_b.risk_frequency} />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.compareWords}</p>
                              <FreqChips
                                rows={(compareQuery.data.segment_b.word_frequency || []).map((w) => ({
                                  label: w.word,
                                  value: w.count,
                                }))}
                                limit={10}
                              />
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.comparePortraitShort}</p>
                              <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                                {compareQuery.data.segment_b.audience_portrait_summary || '—'}
                              </p>
                            </div>
                            <div>
                              <p className="mb-1 font-medium">{ru.batch.comparePrShort}</p>
                              <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                                {compareQuery.data.segment_b.pr_strategy_summary || '—'}
                              </p>
                            </div>
                          </CardContent>
                        </Card>
                      </div>

                      <Card className="shadow-sm">
                        <CardHeader>
                          <CardTitle>{ru.batch.compareDifferences}</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0 sm:px-6">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-[140px]">{ru.batch.compareDimension}</TableHead>
                                <TableHead>{ru.batch.compareSummary}</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {compareQuery.data.differences.map((d, i) => (
                                <TableRow key={i}>
                                  <TableCell className="align-top font-medium">{d.dimension}</TableCell>
                                  <TableCell className="text-sm leading-relaxed">{d.summary}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>

                      <Card className="shadow-sm">
                        <CardHeader>
                          <CardTitle>{ru.batch.comparePrImplications}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={compareQuery.data.pr_implications} />
                        </CardContent>
                      </Card>
                      <DecisionLayerPanel
                        priority_actions={compareQuery.data.priority_actions}
                        impact_effort_matrix={compareQuery.data.impact_effort_matrix}
                        alerts={compareQuery.data.alerts}
                      />
                    </div>
                  )}
                </>
              )}
                </>
              )}
            </TabsContent>

            <TabsContent value="corpus" className="mt-0 space-y-6">
              <p className="text-sm text-muted-foreground">{ru.batch.corpusIntro}</p>
              {!hasInterviewSources ? (
                <p className="text-sm text-muted-foreground">{ru.batch.noSources}</p>
              ) : (
                <>
                  <div className="flex flex-wrap items-end gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{ru.batch.corpusMaxChars}</label>
                      <select
                        className="flex h-9 min-w-[200px] rounded-md border border-input bg-background px-2 text-sm"
                        value={corpusMaxChars}
                        onChange={(e) => setCorpusMaxChars(Number(e.target.value))}
                      >
                        <option value={40_000}>40 000</option>
                        <option value={120_000}>120 000</option>
                        <option value={500_000}>500 000</option>
                        <option value={2_000_000}>2 000 000</option>
                      </select>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={!corpusQuery.data?.text}
                        onClick={async () => {
                          const t = corpusQuery.data?.text ?? '';
                          if (!t) return;
                          try {
                            await navigator.clipboard.writeText(t);
                            setCorpusCopied(true);
                            window.setTimeout(() => setCorpusCopied(false), 2000);
                          } catch {
                            /* ignore */
                          }
                        }}
                      >
                        <Copy className="mr-1 size-3.5" />
                        {corpusCopied ? ru.batch.corpusCopied : ru.batch.corpusCopy}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={!corpusQuery.data?.text}
                        onClick={() => {
                          const t = corpusQuery.data?.text ?? '';
                          if (!t) return;
                          const blob = new Blob([t], { type: 'text/plain;charset=utf-8' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `batch-corpus-${batchId.slice(0, 8)}.txt`;
                          a.click();
                          URL.revokeObjectURL(url);
                        }}
                      >
                        <Download className="mr-1 size-3.5" />
                        {ru.batch.corpusDownload}
                      </Button>
                    </div>
                  </div>
                  {corpusQuery.isPending && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      {ru.batch.loadingAnalysis}
                    </div>
                  )}
                  {corpusQuery.error && <ApiErrorText error={corpusQuery.error} />}
                  {corpusQuery.data && (
                    <div className="space-y-3">
                      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                        <span>
                          {ru.batch.corpusChunkCount}:{' '}
                          <span className="font-medium text-foreground">{corpusQuery.data.chunk_count}</span>
                        </span>
                        <span>
                          {ru.batch.corpusTotalChars}:{' '}
                          <span className="font-medium text-foreground">
                            {corpusQuery.data.total_character_count.toLocaleString('ru-RU')}
                          </span>
                        </span>
                        <span>
                          {ru.batch.corpusMaxChars}:{' '}
                          <span className="font-medium text-foreground">
                            {corpusQuery.data.max_chars_applied.toLocaleString('ru-RU')}
                          </span>
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {corpusQuery.data.chunk_count === 0
                          ? ru.batch.corpusEmpty
                          : corpusQuery.data.truncated
                            ? ru.batch.corpusTruncated
                            : ru.batch.corpusNotTruncated}
                      </p>
                      <Textarea
                        readOnly
                        className="min-h-[320px] font-mono text-xs leading-relaxed"
                        value={corpusQuery.data.text}
                        spellCheck={false}
                      />
                    </div>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value="scenarios" className="mt-0 space-y-6">
              {processingPipelineIncomplete && !strictPrBlocksAi ? (
                <BatchAiProcessingGateCard />
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">{ru.batch.scenarioIntro}</p>
                  <p className="text-sm text-muted-foreground">{ru.batch.scenarioViewModesOnly}</p>
              {!hasInterviewSources ? (
                <p className="text-sm text-muted-foreground">{ru.batch.noSources}</p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={scenarioMode === 'pr_audit' ? 'default' : 'outline'}
                      onClick={() => setScenarioMode('pr_audit')}
                    >
                      {ru.batch.scenarioPrAudit}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={scenarioMode === 'audience' ? 'default' : 'outline'}
                      onClick={() => setScenarioMode('audience')}
                    >
                      {ru.batch.scenarioAudience}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={scenarioMode === 'messaging' ? 'default' : 'outline'}
                      onClick={() => setScenarioMode('messaging')}
                    >
                      {ru.batch.scenarioMessaging}
                    </Button>
                  </div>
                  {scenarioQuery.isPending && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      {ru.batch.loadingAnalysis}
                    </div>
                  )}
                  {scenarioQuery.error && <ApiErrorText error={scenarioQuery.error} />}
                  {scenarioQuery.data &&
                    scenarioQuery.data.mode === scenarioMode &&
                    scenarioQuery.data.pr_audit && (
                    <div className="space-y-4">
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.scenarioBrandPerception}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                            {scenarioQuery.data.pr_audit.brand_perception_summary || '—'}
                          </p>
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.compareRisks}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.pr_audit.risks} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prGaps}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.pr_audit.communication_gaps} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.fullReportRecommendations}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.pr_audit.recommendations} />
                        </CardContent>
                      </Card>
                      <DecisionLayerPanel
                        priority_actions={scenarioQuery.data.pr_audit.priority_actions}
                        impact_effort_matrix={[]}
                        alerts={[]}
                      />
                    </div>
                  )}
                  {scenarioQuery.data &&
                    scenarioQuery.data.mode === scenarioMode &&
                    scenarioQuery.data.audience_insight && (
                    <div className="space-y-4">
                      <AnalysisStatsLine
                        confidence={scenarioQuery.data.audience_insight.confidence}
                        interviewCount={scenarioQuery.data.audience_insight.interview_count}
                        distribution={undefined}
                      />
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.scenarioSegments}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className="text-xs text-muted-foreground">
                            {formatSegmentSnapshot(
                              scenarioQuery.data.audience_insight.audience_snapshot as Record<
                                string,
                                unknown
                              >,
                            )}
                          </p>
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.scenarioPatterns}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc space-y-1 pl-5 text-sm">
                            {(scenarioQuery.data.audience_insight.top_patterns ?? []).map((p, i) => (
                              <li key={i}>
                                {p.text}{' '}
                                <span className="text-muted-foreground">({p.count})</span>
                              </li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.compareWords}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <FreqChips
                            rows={(scenarioQuery.data.audience_insight.word_frequency ?? []).map((w) => ({
                              label: w.word,
                              value: w.count,
                            }))}
                            limit={24}
                          />
                        </CardContent>
                      </Card>
                      {(
                        [
                          ['decision_making', ru.batch.portraitDecision],
                          ['fears', ru.batch.portraitFears],
                          ['trust_drivers', ru.batch.portraitTrust],
                          ['pain_points', ru.batch.portraitPain],
                          ['language_style', ru.batch.portraitLanguage],
                          ['brand_perception', ru.batch.portraitBrand],
                          ['emotional_triggers', ru.batch.portraitEmotional],
                        ] as const
                      ).map(([key, label]) => (
                        <Card key={key} className="shadow-sm">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">{label}</CardTitle>
                          </CardHeader>
                          <CardContent>
                            <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                              {scenarioQuery.data!.audience_insight!.portrait[key]}
                            </p>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                  {scenarioQuery.data &&
                    scenarioQuery.data.mode === scenarioMode &&
                    scenarioQuery.data.messaging_kit && (
                    <div className="space-y-4">
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prTalkingPoints}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.messaging_kit.talking_points} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prMessages}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.messaging_kit.recommended_messages} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.scenarioPhrases}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.messaging_kit.audience_phrases} />
                        </CardContent>
                      </Card>
                      <Card className="shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base">{ru.batch.prMediaHooks}</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <BulletList items={scenarioQuery.data.messaging_kit.media_hooks} />
                        </CardContent>
                      </Card>
                    </div>
                  )}
                </>
              )}
                </>
              )}
            </TabsContent>
          </Tabs>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </>
      )}
    </div>
  );
}
