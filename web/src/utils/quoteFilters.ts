/**
 * Drop filler quotes from PR-facing UI (aligned with backend `is_trivial_quote`).
 */
export function isTrivialQuote(text: string, minLen = 24): boolean {
  const t = text.trim();
  if (!t) return true;
  if (t.length < minLen) return true;
  const lower = t.toLowerCase().replace(/\s+/g, ' ');
  const oneLine = lower.replace(/[.!?…]+$/u, '');
  if (
    /^(?:спасибо|благодарю|окей|ок|да+|нет+|супер|класс|понятно|хорошо|нормально|thanks|thank you|ok|cool|great|nice)(?:\s*[!.]*)?$/iu.test(
      oneLine,
    )
  ) {
    return true;
  }
  if (t.split(/\s+/u).length <= 2 && t.length < 40) return true;
  return false;
}
