"""Filter low-information quotes from PR-facing outputs."""

from __future__ import annotations

import re

# Very short pleasantries / fillers — not evidence for PR narrative.
_TRIVIAL_QUOTE_PATTERNS = re.compile(
    r"^(?:спасибо|благодарю|окей|ок|да+|нет+|супер|класс|понятно|хорошо|нормально|"
    r"thanks|thank you|ok\.?|cool|great|nice)\s*[!.]*$",
    re.IGNORECASE,
)


def is_trivial_quote(text: str, *, min_len: int = 24) -> bool:
    t = (text or "").strip()
    if len(t) < min_len:
        return True
    if _TRIVIAL_QUOTE_PATTERNS.match(t):
        return True
    if len(t.split()) <= 2 and len(t) < 40:
        return True
    return False
