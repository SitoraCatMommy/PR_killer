import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { listDashboardAggregates, listInsights, recomputeDashboardAggregates } from '../api/api';
import { ApiErrorText } from '../components/ApiErrorText';
import type { MessageResponse } from '../api/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatConfidence, ru } from '../i18n/ru';
import { qk } from '../queryKeys';

const DASHBOARD_KIND_RU: Record<string, string> = {
  material_counts: 'Материалы',
  insight_counts: 'Инсайты',
  entity_frequency: 'Частота тем',
  pipeline_health: 'Состояние обработки',
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function PayloadRows({ data, depth = 0 }: { data: unknown; depth?: number }) {
  if (data === null || data === undefined) return <span className="text-muted-foreground">—</span>;
  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="text-muted-foreground">—</span>;
    return (
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {data.map((item, i) => (
          <li key={i}>
            <PayloadRows data={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  if (isPlainObject(data)) {
    const entries = Object.entries(data);
    if (!entries.length) return <span className="text-muted-foreground">—</span>;
    return (
      <dl className={depth > 0 ? 'mt-2 space-y-2 border-l-2 border-border pl-3' : 'space-y-2'}>
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs font-medium text-muted-foreground">{k}</dt>
            <dd className="mt-0.5 text-sm">
              {isPlainObject(v) || Array.isArray(v) ? (
                <PayloadRows data={v} depth={depth + 1} />
              ) : (
                String(v)
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="text-sm">{String(data)}</span>;
}

export function AnalyticsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'overview' | 'insights'>('overview');
  const [msg, setMsg] = useState<MessageResponse | null>(null);

  const aggregates = useQuery({
    queryKey: qk.dashboardAggregates,
    queryFn: listDashboardAggregates,
  });

  const insights = useQuery({
    queryKey: qk.insights(100),
    queryFn: () => listInsights(100),
    enabled: tab === 'insights',
  });

  const recompute = useMutation({
    mutationFn: recomputeDashboardAggregates,
    onSuccess: (m) => {
      setMsg(m);
      void qc.invalidateQueries({ queryKey: qk.dashboardAggregates });
    },
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{ru.analytics.title}</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">{ru.analytics.lede}</p>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'overview' | 'insights')}>
        <TabsList>
          <TabsTrigger value="overview">{ru.analytics.tabOverview}</TabsTrigger>
          <TabsTrigger value="insights">{ru.analytics.tabInsights}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6 space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={recompute.isPending} onClick={() => recompute.mutate()}>
              {recompute.isPending ? ru.analytics.recomputeQueueing : ru.analytics.recompute}
            </Button>
          </div>
          {recompute.error && <ApiErrorText error={recompute.error} />}
          {msg && (
            <p className="text-sm text-muted-foreground">{msg.message}</p>
          )}

          {aggregates.isPending && <Skeleton className="h-48 w-full" />}
          {aggregates.error && <ApiErrorText error={aggregates.error} />}
          {aggregates.data && !aggregates.data.length && (
            <p className="text-sm text-muted-foreground">{ru.analytics.aggregatesEmpty}</p>
          )}
          {aggregates.data && aggregates.data.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {aggregates.data.map((a) => (
                <Card key={a.id} className="shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg">
                      {DASHBOARD_KIND_RU[a.kind] ?? a.kind}
                    </CardTitle>
                    <CardDescription className="font-mono text-xs">
                      {a.period_key} · {ru.analytics.computedAt}: {a.computed_at}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <p className="mb-2 text-xs font-medium text-muted-foreground">
                      {ru.analytics.payload}
                    </p>
                    <PayloadRows data={a.payload as unknown} />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="insights" className="mt-6 space-y-4">
          {insights.isPending && <Skeleton className="h-48 w-full" />}
          {insights.error && <ApiErrorText error={insights.error} />}
          {insights.data && !insights.data.length && (
            <p className="text-sm text-muted-foreground">{ru.analytics.insightsEmpty}</p>
          )}
          {insights.data && insights.data.length > 0 && (
            <ul className="space-y-4">
              {insights.data.map((ins) => (
                <li key={ins.id}>
                  <Card className="shadow-sm">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-lg leading-snug">{ins.headline}</CardTitle>
                      {ins.summary && (
                        <CardDescription>{ins.summary}</CardDescription>
                      )}
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      {typeof ins.confidence === 'number' && (
                        <p className="text-muted-foreground">
                          {ru.analytics.confidence}: {formatConfidence(ins.confidence)}
                        </p>
                      )}
                      {ins.body && <p className="leading-relaxed">{ins.body}</p>}
                      {ins.source_links && ins.source_links.length > 0 && (
                        <ul className="space-y-2 border-t pt-3">
                          {ins.source_links.map((l) => (
                            <li key={l.id}>
                              <Link
                                to={`/materials/${l.material_id}`}
                                className="font-medium text-primary underline-offset-4 hover:underline"
                              >
                                {ru.analytics.linkMaterial}
                              </Link>
                              {l.quote && (
                                <blockquote className="mt-1 border-l-2 border-primary/20 pl-3 text-muted-foreground italic">
                                  {l.quote}
                                </blockquote>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
