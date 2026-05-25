import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ru } from '../i18n/ru';
import type { TracedNavRef, TracedSourceRef } from '../api/types';
import { cn } from '@/lib/utils';

type WordRow = { word: string; count: number };
type PhraseRow = { phrase: string; count: number };

type PrLexQuote = { quote: string; transcript_id: string; chunk_id: string };
type PrLexRow = {
  term: string;
  category: string;
  count: number;
  interview_coverage: number;
  pct: number;
  example_quotes?: PrLexQuote[];
};
type PrLexiconPayload = {
  has_signals?: boolean;
  insufficient_message?: string;
  categories_order?: string[];
  by_category?: Record<string, PrLexRow[]>;
  interview_count?: number;
};
type TraceRow = {
  insight_label?: string;
  pr_signal_type?: string;
  count?: number;
  source_ids?: string[];
  sample_quote?: string;
  open_source_link?: Record<string, unknown>;
};

function openLinkToTraceRef(open?: Record<string, unknown>): TracedSourceRef | null {
  if (!open || typeof open !== 'object') return null;
  const n = open as TracedNavRef;
  if (n.kind === 'document' && n.document_id) {
    return {
      entity_id: '',
      source_document_id: n.document_id,
      source_audio_id: null,
      transcript_id: null,
      chunk_id: n.chunk_id ?? null,
      nav: n,
    };
  }
  if ((n.kind === 'audio' || n.kind === 'transcript') && n.audio_id) {
    return {
      entity_id: '',
      source_document_id: null,
      source_audio_id: n.audio_id,
      transcript_id: n.transcript_id ?? null,
      chunk_id: n.chunk_id ?? null,
      nav: n,
    };
  }
  return null;
}

function traceNavHref(ref: TracedSourceRef): string | null {
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

type SortState = { key: string; dir: 'asc' | 'desc' };

function useSortedFiltered<T extends Record<string, unknown>>(
  rows: T[],
  search: string,
  sort: SortState | null,
  searchKeys: (keyof T)[],
) {
  return useMemo(() => {
    const q = search.trim().toLowerCase();
    let out = rows;
    if (q) {
      out = out.filter((r) =>
        searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(q)),
      );
    }
    if (!sort) return out;
    const mult = sort.dir === 'asc' ? 1 : -1;
    const k = sort.key as keyof T;
    return [...out].sort((a, b) => {
      const va = a[k];
      const vb = b[k];
      if (typeof va === 'number' && typeof vb === 'number') return mult * (va - vb);
      return mult * String(va ?? '').localeCompare(String(vb ?? ''), undefined, { numeric: true });
    });
  }, [rows, search, sort, searchKeys]);
}

function heatColor(count: number, max: number): string {
  if (max <= 0 || count <= 0) return 'bg-muted/40';
  const t = Math.min(1, count / max);
  if (t > 0.66) return 'bg-rose-600/85 text-white';
  if (t > 0.33) return 'bg-amber-500/70 text-foreground';
  return 'bg-emerald-600/35 text-foreground';
}

export function BatchDashboardResearchWidgets({
  evidenceDashboard,
  fallbackWordFreq,
  fallbackPatterns,
  dashGroupBy,
}: {
  evidenceDashboard?: Record<string, unknown>;
  fallbackWordFreq: WordRow[];
  fallbackPatterns: { text: string; count: number }[];
  dashGroupBy: string;
}) {
  const wpt = (evidenceDashboard?.word_phrase_tables ?? null) as {
    words?: WordRow[];
    bigrams?: PhraseRow[];
    trigrams?: PhraseRow[];
    stopword_filter?: boolean;
  } | null;

  const words = wpt?.words?.length ? wpt.words : fallbackWordFreq;
  const bigrams = wpt?.bigrams ?? [];
  const trigrams = wpt?.trigrams ?? [];
  const phrases: PhraseRow[] = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of bigrams) m.set(p.phrase, (m.get(p.phrase) ?? 0) + p.count);
    for (const p of trigrams) m.set(p.phrase, (m.get(p.phrase) ?? 0) + p.count);
    const merged = [...m.entries()].map(([phrase, count]) => ({ phrase, count })).sort((a, b) => b.count - a.count);
    if (merged.length) return merged;
    return fallbackPatterns.map((p) => ({ phrase: p.text, count: p.count }));
  }, [bigrams, trigrams, fallbackPatterns]);

  const traceRows = (
    ((evidenceDashboard?.traceability ?? {}) as { rows?: TraceRow[] }).rows ?? []
  ) as TraceRow[];

  const stacked =
    (evidenceDashboard?.sentiment_stacked_by_segment ?? []) as Array<{
      segment?: string;
      positive?: number;
      negative?: number;
      positive_pct?: number;
      negative_pct?: number;
    }>;

  const heat = (evidenceDashboard?.risk_heatmap ?? {}) as {
    columns?: Array<{ pr_signal_type?: string }>;
    rows?: Array<{ segment?: string; cells?: Array<{ pr_signal_type?: string; count?: number }> }>;
  };

  const heatMax = useMemo(() => {
    let m = 0;
    for (const r of heat.rows ?? []) {
      for (const c of r.cells ?? []) m = Math.max(m, Number(c.count ?? 0));
    }
    return m;
  }, [heat.rows]);

  const pls = evidenceDashboard?.pr_lexicon_signals as PrLexiconPayload | undefined;
  const usePrLexicon = pls != null;
  const [prLexTab, setPrLexTab] = useState<string>('trust');

  const prLexCatLabel = useMemo(
    () => ({
      trust: ru.batch.prLexCatTrust,
      risk: ru.batch.prLexCatRisk,
      convenience: ru.batch.prLexCatConvenience,
      negative: ru.batch.prLexCatNegative,
      money: ru.batch.prLexCatMoney,
      brand: ru.batch.prLexCatBrand,
    }),
    [],
  );

  const [wSearch, setWSearch] = useState('');
  const [wSort, setWSort] = useState<SortState | null>({ key: 'count', dir: 'desc' });
  const wordsView = useSortedFiltered(
    words.map((x) => ({ word: x.word, count: x.count })) as unknown as Record<string, unknown>[],
    wSearch,
    wSort,
    ['word'],
  ) as unknown as WordRow[];

  const [pSearch, setPSearch] = useState('');
  const [pSort, setPSort] = useState<SortState | null>({ key: 'count', dir: 'desc' });
  const phraseView = useSortedFiltered(
    phrases.map((x) => ({ phrase: x.phrase, count: x.count })) as unknown as Record<string, unknown>[],
    pSearch,
    pSort,
    ['phrase'],
  ) as unknown as PhraseRow[];

  const [tSearch, setTSearch] = useState('');
  const [tSort, setTSort] = useState<SortState | null>({ key: 'count', dir: 'desc' });
  const traceView = useSortedFiltered(
    traceRows.map((r) => ({
      insight_label: r.insight_label ?? '',
      pr_signal_type: r.pr_signal_type ?? '',
      count: Number(r.count ?? 0),
      source_ids: (r.source_ids ?? []).join(', '),
      sample_quote: r.sample_quote ?? '',
      _raw: r,
    })) as unknown as Record<string, unknown>[],
    tSearch,
    tSort,
    ['insight_label', 'pr_signal_type', 'sample_quote', 'source_ids'],
  );

  const toggleSort = (prev: SortState | null, key: string): SortState => {
    if (!prev || prev.key !== key) return { key, dir: 'desc' };
    return { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' };
  };

  return (
    <div className="space-y-8 border-t pt-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ru.batch.sentimentStackedTitle}</CardTitle>
            <CardDescription>
              {!dashGroupBy ? ru.batch.sentimentStackedNeedGroup : ru.batch.sentimentStackedHint}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {stacked.length === 0 ? (
              <p className="text-sm text-muted-foreground">—</p>
            ) : (
              stacked.map((row, i) => {
                const pos = Number(row.positive ?? 0);
                const neg = Number(row.negative ?? 0);
                const tot = pos + neg || 1;
                const pw = Math.round((100 * pos) / tot);
                const nw = Math.round((100 * neg) / tot);
                return (
                  <div key={i} className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{String(row.segment ?? '—')}</span>
                      <span>
                        +{row.positive_pct ?? Math.round((100 * pos) / tot)}% / −
                        {row.negative_pct ?? Math.round((100 * neg) / tot)}%
                      </span>
                    </div>
                    <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="bg-emerald-600/80"
                        style={{ width: `${pw}%` }}
                        title={`positive ${pos}`}
                      />
                      <div
                        className="bg-rose-600/75"
                        style={{ width: `${nw}%` }}
                        title={`negative ${neg}`}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ru.batch.riskHeatmapTitle}</CardTitle>
            <CardDescription>
              {!dashGroupBy ? ru.batch.riskHeatmapNeedGroup : ru.batch.riskHeatmapHint}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {(heat.rows ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">—</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[140px]">{ru.batch.riskHeatmapSegment}</TableHead>
                    {(heat.columns ?? []).map((c, j) => (
                      <TableHead key={j} className="text-center text-xs font-medium">
                        {c.pr_signal_type ?? '—'}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(heat.rows ?? []).map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-xs font-medium">{r.segment ?? '—'}</TableCell>
                      {(r.cells ?? []).map((c, j) => (
                        <TableCell key={j} className="p-1 text-center">
                          <span
                            className={cn(
                              'inline-flex min-w-[2rem] justify-center rounded px-2 py-1 text-xs tabular-nums',
                              heatColor(Number(c.count ?? 0), heatMax),
                            )}
                          >
                            {c.count ?? 0}
                          </span>
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        {usePrLexicon ? (
          <Card className="shadow-sm xl:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{ru.batch.prLexiconTitle}</CardTitle>
              <CardDescription>{ru.batch.prLexiconHint}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {!pls?.has_signals ? (
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {pls?.insufficient_message ?? ru.batch.prLexiconEmpty}
                </p>
              ) : (
                <Tabs value={prLexTab} onValueChange={setPrLexTab} className="space-y-3">
                  <TabsList variant="line" className="h-auto min-h-9 w-full flex-wrap justify-start gap-1">
                    {(pls.categories_order ?? ['trust', 'risk', 'convenience', 'negative', 'money', 'brand']).map(
                      (c) => (
                        <TabsTrigger key={c} value={c} className="text-xs">
                          {prLexCatLabel[c as keyof typeof prLexCatLabel] ?? c}
                        </TabsTrigger>
                      ),
                    )}
                  </TabsList>
                  {(pls.categories_order ?? ['trust', 'risk', 'convenience', 'negative', 'money', 'brand']).map(
                    (c) => (
                      <TabsContent key={c} value={c} className="mt-0 space-y-2">
                        <div className="max-h-[360px] overflow-auto rounded-md border">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="text-xs">{ru.batch.prLexColTerm}</TableHead>
                                <TableHead className="text-right text-xs">{ru.batch.prLexColCount}</TableHead>
                                <TableHead className="text-right text-xs">{ru.batch.prLexColCoverage}</TableHead>
                                <TableHead className="text-xs">{ru.batch.prLexColQuotes}</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {(pls.by_category?.[c] ?? []).length === 0 ? (
                                <TableRow>
                                  <TableCell colSpan={4} className="text-xs text-muted-foreground">
                                    {ru.batch.prLexCatEmpty}
                                  </TableCell>
                                </TableRow>
                              ) : (
                                (pls.by_category?.[c] ?? []).map((row, i) => (
                                  <TableRow key={`${row.term}-${i}`}>
                                    <TableCell className="text-xs font-medium leading-snug">{row.term}</TableCell>
                                    <TableCell className="text-right tabular-nums text-xs">{row.count}</TableCell>
                                    <TableCell className="text-right tabular-nums text-xs">
                                      {row.interview_coverage}
                                      <span className="text-muted-foreground"> ({row.pct}%)</span>
                                    </TableCell>
                                    <TableCell className="text-xs text-muted-foreground">
                                      {(row.example_quotes ?? []).slice(0, 3).map((q, j) => (
                                        <p key={j} className="mb-1.5 border-b border-border/40 pb-1.5 last:border-0">
                                          {q.quote}
                                          {(q.transcript_id || q.chunk_id) && (
                                            <span className="mt-0.5 block text-[10px] font-mono opacity-80">
                                              tr:{q.transcript_id || '—'} · ch:{q.chunk_id || '—'}
                                            </span>
                                          )}
                                        </p>
                                      ))}
                                    </TableCell>
                                  </TableRow>
                                ))
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      </TabsContent>
                    ),
                  )}
                </Tabs>
              )}
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className="shadow-sm xl:col-span-1">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{ru.batch.tableWordFreq}</CardTitle>
                {wpt ? (
                  <CardDescription>
                    {wpt.stopword_filter ? ru.batch.stopwordsOn : ru.batch.stopwordsOff}
                  </CardDescription>
                ) : null}
              </CardHeader>
              <CardContent className="space-y-2">
                <Input
                  placeholder={ru.batch.tableSearchPlaceholder}
                  value={wSearch}
                  onChange={(e) => setWSearch(e.target.value)}
                  className="h-8 text-sm"
                />
                <div className="max-h-[280px] overflow-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead
                          className="cursor-pointer text-xs"
                          onClick={() => setWSort((p) => toggleSort(p, 'word'))}
                        >
                          {ru.batch.colWord} {wSort?.key === 'word' ? (wSort.dir === 'asc' ? '↑' : '↓') : ''}
                        </TableHead>
                        <TableHead
                          className="cursor-pointer text-right text-xs"
                          onClick={() => setWSort((p) => toggleSort(p, 'count'))}
                        >
                          {ru.batch.colCount} {wSort?.key === 'count' ? (wSort.dir === 'asc' ? '↑' : '↓') : ''}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {wordsView.map((w, i) => (
                        <TableRow key={`${w.word}-${i}`}>
                          <TableCell className="font-mono text-xs">{w.word}</TableCell>
                          <TableCell className="text-right tabular-nums text-xs">{w.count}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-sm xl:col-span-1">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{ru.batch.tableKeyPhrases}</CardTitle>
                <CardDescription>{ru.batch.tableKeyPhrasesHint}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <Input
                  placeholder={ru.batch.tableSearchPlaceholder}
                  value={pSearch}
                  onChange={(e) => setPSearch(e.target.value)}
                  className="h-8 text-sm"
                />
                <div className="max-h-[280px] overflow-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead
                          className="cursor-pointer text-xs"
                          onClick={() => setPSort((p) => toggleSort(p, 'phrase'))}
                        >
                          {ru.batch.colPhrase}{' '}
                          {pSort?.key === 'phrase' ? (pSort.dir === 'asc' ? '↑' : '↓') : ''}
                        </TableHead>
                        <TableHead
                          className="cursor-pointer text-right text-xs"
                          onClick={() => setPSort((p) => toggleSort(p, 'count'))}
                        >
                          {ru.batch.colCount} {pSort?.key === 'count' ? (pSort.dir === 'asc' ? '↑' : '↓') : ''}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {phraseView.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={2} className="text-xs text-muted-foreground">
                            {ru.batch.tablePhrasesEmpty}
                          </TableCell>
                        </TableRow>
                      ) : (
                        phraseView.map((p, i) => (
                          <TableRow key={`${p.phrase}-${i}`}>
                            <TableCell className="text-xs leading-snug">{p.phrase}</TableCell>
                            <TableCell className="text-right tabular-nums text-xs">{p.count}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </>
        )}

        <Card className="shadow-sm xl:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ru.batch.tableTraceability}</CardTitle>
            <CardDescription>{ru.batch.tableTraceabilityHint}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Input
              placeholder={ru.batch.tableSearchPlaceholder}
              value={tSearch}
              onChange={(e) => setTSearch(e.target.value)}
              className="h-8 text-sm"
            />
            <div className="max-h-[320px] overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className="cursor-pointer text-xs"
                      onClick={() => setTSort((p) => toggleSort(p, 'insight_label'))}
                    >
                      {ru.batch.colInsight}{' '}
                      {tSort?.key === 'insight_label' ? (tSort.dir === 'asc' ? '↑' : '↓') : ''}
                    </TableHead>
                    <TableHead
                      className="cursor-pointer text-xs"
                      onClick={() => setTSort((p) => toggleSort(p, 'pr_signal_type'))}
                    >
                      PR {tSort?.key === 'pr_signal_type' ? (tSort.dir === 'asc' ? '↑' : '↓') : ''}
                    </TableHead>
                    <TableHead
                      className="cursor-pointer text-right text-xs"
                      onClick={() => setTSort((p) => toggleSort(p, 'count'))}
                    >
                      # {tSort?.key === 'count' ? (tSort.dir === 'asc' ? '↑' : '↓') : ''}
                    </TableHead>
                    <TableHead className="text-xs">{ru.batch.colSource}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {traceView.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-xs text-muted-foreground">
                        —
                      </TableCell>
                    </TableRow>
                  ) : (
                    traceView.map((tv, i) => {
                      const raw = tv._raw as TraceRow;
                      const ref = openLinkToTraceRef(raw.open_source_link);
                      const href = ref ? traceNavHref(ref) : null;
                      return (
                        <TableRow key={i}>
                          <TableCell className="max-w-[140px] text-xs leading-snug">
                            {String(tv.insight_label ?? '').slice(0, 200)}
                          </TableCell>
                          <TableCell className="text-xs">{String(tv.pr_signal_type ?? '')}</TableCell>
                          <TableCell className="text-right tabular-nums text-xs">
                            {String(Number(tv.count ?? 0))}
                          </TableCell>
                          <TableCell className="space-y-1">
                            <p className="text-[10px] text-muted-foreground line-clamp-3">
                              {String(tv.sample_quote ?? '').slice(0, 220)}
                            </p>
                            {href ? (
                              <Link
                                to={href}
                                className="text-[10px] font-medium text-primary underline-offset-2 hover:underline"
                              >
                                {ru.batch.openTracedSource}
                              </Link>
                            ) : null}
                            <p className="font-mono text-[9px] text-muted-foreground/90 line-clamp-2">
                              {String(tv.source_ids ?? '')}
                            </p>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function PrRiskTrendIcon({ trend }: { trend: string }) {
  const t = (trend || 'stable').toLowerCase();
  if (t === 'up') return <ArrowUp className="size-3.5 text-rose-600" aria-hidden />;
  if (t === 'down') return <ArrowDown className="size-3.5 text-emerald-600" aria-hidden />;
  return <Minus className="size-3.5 text-muted-foreground" aria-hidden />;
}

export function evidenceRefHref(e: {
  source_document_id?: string | null;
  source_audio_id?: string | null;
  chunk_id?: string | null;
}): string | null {
  if (e.source_document_id) {
    return `/sources/documents/${e.source_document_id}${e.chunk_id ? `?chunk=${encodeURIComponent(e.chunk_id)}` : ''}`;
  }
  if (e.source_audio_id) {
    return `/sources/audios/${e.source_audio_id}`;
  }
  return null;
}
