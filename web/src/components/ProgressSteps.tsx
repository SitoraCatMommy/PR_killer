import { cn } from '@/lib/utils';
import { ru } from '../i18n/ru';

export type ProgressStepsState = {
  hasData: boolean;
  touchedProcessing: boolean;
  /** Latest structured research report is ready */
  hasReport: boolean;
  hasSummary: boolean;
};

/** Компактная полоса шагов в духе Notion/Linear (4 этапа). */
export function ProgressSteps(s: ProgressStepsState) {
  const steps = [
    { key: 1, label: ru.progress.stepData, done: s.hasData, current: !s.hasData },
    {
      key: 2,
      label: ru.progress.stepProcess,
      done: s.touchedProcessing,
      current: s.hasData && !s.touchedProcessing,
    },
    {
      key: 3,
      label: ru.progress.stepReport,
      done: s.hasReport,
      current: s.touchedProcessing && !s.hasReport,
    },
    {
      key: 4,
      label: ru.progress.stepOutcome,
      done: s.hasSummary,
      current: s.hasReport && !s.hasSummary,
    },
  ] as const;

  return (
    <nav
      className="mb-8 flex flex-wrap items-center gap-1 text-sm text-muted-foreground"
      aria-label={ru.progress.ariaLabel}
    >
      {steps.map((st, i) => (
        <span key={st.key} className="flex items-center gap-1">
          {i > 0 && (
            <span className="mx-1 text-border select-none" aria-hidden>
              →
            </span>
          )}
          <span
            className={cn(
              'rounded-md px-2 py-0.5 font-medium transition-colors',
              st.done && 'bg-secondary text-secondary-foreground',
              st.current && !st.done && 'bg-primary text-primary-foreground',
              !st.done && !st.current && 'text-muted-foreground',
            )}
          >
            {st.done ? '✓ ' : ''}
            {st.label}
          </span>
        </span>
      ))}
    </nav>
  );
}
