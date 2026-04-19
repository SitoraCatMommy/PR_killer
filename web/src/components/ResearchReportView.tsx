import type { ReportExtrasJson, ResearchReportRead } from '../api/types';
import { ru } from '../i18n/ru';
import { isTrivialQuote } from '../utils/quoteFilters';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function extrasFrom(report: ResearchReportRead): ReportExtrasJson {
  const raw = report.report_extras_json;
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as ReportExtrasJson;
  }
  return {};
}

function renderListBlock(title: string, items: unknown) {
  const arr = Array.isArray(items) ? items : [];
  if (!arr.length) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">
          {arr.map((row, i) => {
            if (typeof row === 'string') {
              return <li key={i}>{row}</li>;
            }
            if (isObj(row)) {
              const text =
                (typeof row.text === 'string' && row.text) ||
                (typeof row.content === 'string' && row.content) ||
                JSON.stringify(row);
              return <li key={i}>{text}</li>;
            }
            return <li key={i}>{String(row)}</li>;
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function topWordEntries(freq: Record<string, number> | undefined, n: number): [string, number][] {
  if (!freq || typeof freq !== 'object') return [];
  return Object.entries(freq)
    .filter(([, c]) => typeof c === 'number')
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

function WordAnalysisSection({ extras }: { extras: ReportExtrasJson }) {
  const wa = extras.word_analysis;
  if (!wa || typeof wa !== 'object') return null;
  const interp = typeof wa.pr_interpretation === 'string' ? wa.pr_interpretation.trim() : '';
  const dominantLex =
    typeof wa.dominant_lexicon_pr_perception === 'string'
      ? wa.dominant_lexicon_pr_perception.trim()
      : '';
  const risk = typeof wa.risk_signal_strength === 'string' ? wa.risk_signal_strength : '';
  const balance = typeof wa.trust_vs_risk_balance === 'string' ? wa.trust_vs_risk_balance : '';
  const top = topWordEntries(wa.word_frequency, 18);
  if (!interp && !dominantLex && !top.length && !risk && !balance) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg">{ru.project.reportWordAnalysis}</CardTitle>
        <CardDescription>{ru.project.reportWordAnalysisHint}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {(risk || balance) && (
          <div className="flex flex-wrap gap-2">
            {risk ? (
              <Badge variant="secondary">
                {ru.project.reportRiskSignal}: {risk}
              </Badge>
            ) : null}
            {balance ? (
              <Badge variant="outline">
                {ru.project.reportTrustRiskBalance}: {balance}
              </Badge>
            ) : null}
          </div>
        )}
        {dominantLex ? (
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {ru.project.reportDominantLexiconPr}
            </p>
            <p className="leading-relaxed text-foreground/90">{dominantLex}</p>
          </div>
        ) : null}
        {interp ? <p className="leading-relaxed text-foreground/90">{interp}</p> : null}
        {top.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {ru.project.reportTopTerms}
            </p>
            <ul className="flex flex-wrap gap-2">
              {top.map(([w, c]) => (
                <li key={w}>
                  <Badge variant="outline" className="font-normal">
                    {w} <span className="text-muted-foreground">×{c}</span>
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SupportingQuotesSection({ items }: { items: unknown }) {
  const arr = Array.isArray(items) ? items : [];
  if (!arr.length) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg">{ru.project.reportSupportingQuotes}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {arr.map((row, i) => {
          if (!isObj(row)) return null;
          const quote = typeof row.quote === 'string' ? row.quote : null;
          const note = typeof row.note === 'string' ? row.note : null;
          if (!quote || isTrivialQuote(quote)) return null;
          return (
            <blockquote key={i} className="border-l-2 border-primary/30 pl-4 text-sm leading-relaxed">
              <p className="whitespace-pre-wrap italic text-foreground/95">«{quote}»</p>
              {note ? <p className="mt-2 text-muted-foreground">{note}</p> : null}
            </blockquote>
          );
        })}
      </CardContent>
    </Card>
  );
}

function ExternalInReportSection({ items }: { items: unknown }) {
  const arr = Array.isArray(items) ? items : [];
  if (!arr.length) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg">{ru.project.reportExternalMaterials}</CardTitle>
        <CardDescription>{ru.project.reportExternalHint}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {arr.map((row, i) => {
          if (!isObj(row)) return null;
          const title = typeof row.title === 'string' ? row.title : `Материал ${i + 1}`;
          const url = typeof row.url === 'string' ? row.url : '';
          const summary = typeof row.summary === 'string' ? row.summary : null;
          const why =
            (typeof row.why_relevant_for_pr === 'string' && row.why_relevant_for_pr) ||
            (typeof row.relevance === 'string' && row.relevance) ||
            null;
          return (
            <div key={i} className="rounded-md border border-border/60 p-4">
              <p className="font-medium leading-snug">
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
              </p>
              {why ? (
                <p className="mt-2 text-sm text-foreground/90">
                  <span className="font-medium text-muted-foreground">{ru.project.externalWhyPr}: </span>
                  {why}
                </p>
              ) : null}
              {summary ? <p className="mt-2 text-sm text-muted-foreground">{summary}</p> : null}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function prListSection(title: string, hint: string | undefined, items: unknown) {
  const arr = Array.isArray(items) ? items.filter((x) => String(x).trim()) : [];
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
        {hint ? <CardDescription>{hint}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        {arr.length ? (
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">
            {arr.map((row, i) => (
              <li key={i}>{typeof row === 'string' ? row : String(row)}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{ru.project.reportPrBlockEmpty}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function ResearchReportView({ report }: { report: ResearchReportRead }) {
  const extras = extrasFrom(report);
  return (
    <div className="space-y-6">
      <Card className="shadow-sm border-primary/20">
        <CardHeader>
          <CardTitle className="text-xl">{report.title}</CardTitle>
          {report.description && (
            <CardDescription className="text-base text-foreground/90">{report.description}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {ru.project.reportExecutiveSummary}
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{report.executive_summary}</p>
        </CardContent>
      </Card>

      {renderListBlock(ru.project.reportKeyFindings, report.key_findings_json)}
      {renderListBlock(ru.project.reportProblems, report.problems_json)}
      {renderListBlock(ru.project.reportPatterns, report.patterns_json)}
      {renderListBlock(ru.project.reportRisks, report.risks_json)}
      {renderListBlock(ru.project.reportHypotheses, report.hypotheses_json)}
      {renderListBlock(ru.project.reportRecommendations, report.recommendations_json)}
      {renderListBlock(ru.project.reportForecast, report.forecast_json)}
      {renderListBlock(ru.project.reportNextSteps, report.next_steps_json)}

      {prListSection(
        ru.project.reportTalkingPoints,
        ru.project.reportTalkingPointsHint,
        extras.talking_points,
      )}
      {prListSection(
        ru.project.reportReputationalRisksBlock,
        ru.project.reportReputationalRisksHint,
        extras.reputational_risks,
      )}
      {prListSection(
        ru.project.reportCommunicationGapsBlock,
        ru.project.reportCommunicationGapsHint,
        extras.communication_gaps,
      )}
      {prListSection(
        ru.project.reportNextStepsPrBlock,
        ru.project.reportNextStepsPrHint,
        extras.next_steps_pr,
      )}
      {renderListBlock(ru.project.reportInfopovody, extras.infopovody)}
      {renderListBlock(ru.project.reportOpenQuestions, extras.open_questions)}

      <WordAnalysisSection extras={extras} />
      <ExternalInReportSection items={report.external_articles_json} />
      <SupportingQuotesSection items={report.supporting_quotes_json} />
    </div>
  );
}
