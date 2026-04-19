import type { ResearchSummaryRead } from '../api/types';
import { ru } from '../i18n/ru';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

const SUMMARY_STATUS_RU: Record<string, string> = {
  draft: 'Черновик',
  generating: 'Формируется',
  ready: 'Готово',
  stale: 'Требует обновления',
  failed: 'Ошибка при формировании',
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/** Превращает JSON-поля сводки в списки без «стены» из JSON. */
function SummaryListSection({ title, data }: { title: string; data: unknown }) {
  if (data === null || data === undefined) return null;

  if (Array.isArray(data)) {
    if (data.length === 0) return null;
    const items = data.map((item, i) => {
      if (item === null || item === undefined) return null;
      if (typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
        return (
          <li key={i} className="text-sm leading-relaxed">
            {String(item)}
          </li>
        );
      }
      if (isPlainObject(item)) {
        const entries = Object.entries(item).filter(([, v]) => v != null && v !== '');
        if (entries.length === 0) return null;
        return (
          <li key={i} className="text-sm">
            <ul className="mt-1 list-none space-y-1 border-l-2 border-border pl-3">
              {entries.map(([k, v]) => (
                <li key={k}>
                  <span className="font-medium text-foreground">{k}</span>
                  {': '}
                  <span className="text-muted-foreground">
                    {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        );
      }
      return (
        <li key={i} className="text-sm text-muted-foreground">
          {JSON.stringify(item)}
        </li>
      );
    });
    if (!items.some(Boolean)) return null;
    return (
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-2 pl-5">{items}</ul>
        </CardContent>
      </Card>
    );
  }

  if (isPlainObject(data)) {
    const entries = Object.entries(data);
    if (entries.length === 0) return null;
    return (
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-2 text-sm">
            {entries.map(([k, v]) => (
              <div key={k} className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
                <dt className="shrink-0 font-medium text-foreground">{k}</dt>
                <dd className="text-muted-foreground">
                  {typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed">{String(data)}</p>
      </CardContent>
    </Card>
  );
}

export function SummaryOutcome({ summary }: { summary: ResearchSummaryRead }) {
  const statusLabel = SUMMARY_STATUS_RU[summary.status] ?? summary.status;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">{ru.project.outcomeStatus}</span>
        <Badge variant="secondary">{statusLabel}</Badge>
      </div>

      {summary.summary_text?.trim() ? (
        <Card className="border-primary/20 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">{ru.project.outcomeOverview}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none text-foreground dark:prose-invert">
              <p className="whitespace-pre-wrap leading-relaxed">{summary.summary_text}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Separator />

      <div className="grid gap-3">
        <SummaryListSection title={ru.project.outcomeKeyFindings} data={summary.key_findings_json} />
        <SummaryListSection title={ru.project.outcomeFacts} data={summary.facts_json} />
        <SummaryListSection title={ru.project.outcomeHypotheses} data={summary.hypotheses_json} />
        <SummaryListSection title={ru.project.outcomeRisks} data={summary.risks_json} />
        <SummaryListSection title={ru.project.outcomeOpportunities} data={summary.opportunities_json} />
        <SummaryListSection title={ru.project.outcomeRecommendations} data={summary.recommendations_json} />
        <SummaryListSection title={ru.project.outcomeOpenQuestions} data={summary.open_questions_json} />
      </div>
    </div>
  );
}
