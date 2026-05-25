import type { OutputLanguage } from '../api/types';

const VALID: ReadonlySet<OutputLanguage> = new Set(['ru', 'uz', 'en']);

/** Safe ru|uz|en for API and UI; never throws. */
export function normalizeOutputLanguage(raw: string | null | undefined, fallback: OutputLanguage = 'ru'): OutputLanguage {
  const v = (raw ?? '').toString().trim().toLowerCase();
  if (VALID.has(v as OutputLanguage)) return v as OutputLanguage;
  return fallback;
}
