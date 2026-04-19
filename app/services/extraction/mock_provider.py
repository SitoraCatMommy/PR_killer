"""Deterministic sentence-level extraction: multiple structured entities per chunk (no full-chunk passthrough)."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from app.domain.enums import EntityType
from app.schemas.research_extraction import ExtractedEntityCandidate

# INSIGHT / RECOMMENDATION: no separate enum — use CLAIM + CUSTOM with extraction_role tags.


def _mask_urls_emails_for_split(text: str) -> str:
    """Replace URL/email spans with spaces so dots inside domains do not break sentence split."""
    masked = text
    for m in list(_URL_SPLIT.finditer(text))[::-1]:
        masked = masked[: m.start()] + " " * (m.end() - m.start()) + masked[m.end() :]
    for m in list(_EMAIL_SPLIT.finditer(text))[::-1]:
        masked = masked[: m.start()] + " " * (m.end() - m.start()) + masked[m.end() :]
    return masked


_URL_SPLIT = re.compile(r"https?://[^\s<>()\[\]]+[^\s<>()\[\].,;:\"']", re.IGNORECASE)
_EMAIL_SPLIT = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Split on . ! ? or newlines; spans map to original `text` (URLs/emails masked first)."""
    text = text.strip()
    if not text:
        return []
    masked = _mask_urls_emails_for_split(text)
    out: list[tuple[str, int, int]] = []
    for m in re.finditer(r"[^.!?\n]+(?:[.!?]+(?=\s|$)|(?=\n)|$)", masked):
        s0, s1 = m.start(), m.end()
        seg = text[s0:s1].strip()
        if not seg:
            continue
        out.append((seg, s0, s1))
    if not out:
        return [(text, 0, len(text))]
    return out


def _expand_sentence_fragments(sent: str, abs_start: int, abs_end: int) -> list[tuple[str, int, int]]:
    """
    Further split a sentence into clauses so a single long sentence can yield several entities.
    Spans are absolute in the chunk.
    """
    sent = sent.strip()
    if not sent:
        return []

    if ";" in sent:
        parts: list[tuple[str, int, int]] = []
        cursor = 0
        for piece in re.split(r"\s*;\s*", sent):
            piece = piece.strip()
            if not piece:
                continue
            idx = sent.find(piece, cursor)
            if idx < 0:
                idx = sent.find(piece)
            if idx < 0:
                continue
            a = abs_start + idx
            b = a + len(piece)
            cursor = idx + len(piece)
            parts.append((piece, a, b))
        return parts if parts else [(sent, abs_start, abs_end)]

    if len(sent) > 90 and sent.count(",") >= 2:
        pieces = re.split(r",\s*", sent)
        if len(pieces) < 2:
            return [(sent, abs_start, abs_end)]
        out: list[tuple[str, int, int]] = []
        cursor = 0
        for piece in pieces[:6]:
            piece = piece.strip()
            if len(piece) < 12:
                continue
            idx = sent.find(piece, cursor)
            if idx < 0:
                idx = sent.find(piece)
            if idx < 0:
                continue
            a = abs_start + idx
            b = a + len(piece)
            cursor = idx + len(piece)
            out.append((piece, a, b))
        return out if len(out) >= 2 else [(sent, abs_start, abs_end)]

    return [(sent, abs_start, abs_end)]


def _even_segments(text: str, n: int) -> list[tuple[int, int]]:
    L = len(text)
    if n <= 1 or L == 0:
        return [(0, L)]
    n = min(n, L)
    step = max(1, L // n)
    out: list[tuple[int, int]] = []
    for i in range(n):
        a = i * step
        b = L if i == n - 1 else min(L, (i + 1) * step)
        if b > a:
            out.append((a, b))
    return out


def _clip(s: str, max_len: int = 300) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def _title_from_sentence(sentence: str, fallback: str, max_len: int = 120) -> str:
    s = sentence.strip()
    if not s:
        return fallback[:512]
    line = s.split("\n", 1)[0].strip()
    return (_clip(line, max_len)[:512] or fallback[:512])


class MockResearchExtractionProvider:
    """
    Per-sentence rules → multiple ExtractedEntityCandidate rows per chunk.
    URLs/emails add extra FACT rows; each sentence adds one semantic row.
    """

    _URL = re.compile(r"https?://[^\s<>()\[\]]+[^\s<>()\[\].,;:\"']", re.IGNORECASE)
    _EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    _NUMBER = re.compile(
        r"\b\d+(?:[.,]\d+)*(?:\s*%|\s*percent\b|\b(?:k|m|b)\b)?|\b\d{1,3}(?:,\d{3})+\b",
        re.IGNORECASE,
    )

    _REC_START = re.compile(
        r"^\s*(recommendation\b|we\s+suggest\b|we\s+should\b|should\b)",
        re.IGNORECASE,
    )
    _HYP_START = re.compile(
        r"^\s*(there\s+is\s+a\s+hypothesis\b|we\s+believe\b|it\s+could\b|might\b)",
        re.IGNORECASE,
    )
    _PROBLEM = re.compile(
        r"\b(pain|struggle|confus|difficult|problem|issue|broken|annoy|frustrat)\b",
        re.IGNORECASE,
    )
    _RISK = re.compile(
        r"\b(risks?|fear|may\s+switch|error|uncertain)\b",
        re.IGNORECASE,
    )
    _OPP = re.compile(
        r"\b(opportunity|potential|could\s+introduce)\b",
        re.IGNORECASE,
    )
    _INSIGHT = re.compile(
        r"\b(users?|we\s+observed|common\s+issue)\b",
        re.IGNORECASE,
    )

    def _confidence(self, chunk_index: int, slot: int) -> float:
        h = hashlib.sha256(f"mock-extract-v3:{chunk_index}:{slot}".encode()).hexdigest()
        n = int(h[:8], 16) % 351
        return round(min(0.95, 0.6 + n / 1000.0), 3)

    def _evidence(self, chunk: str, start: int, end: int) -> dict:
        quote = chunk[start:end].strip()
        return {
            "quote": _clip(quote, 300),
            "span_start": start,
            "span_end": end,
            "provider": "mock_sentence",
        }

    def _append(
        self,
        collected: list[ExtractedEntityCandidate],
        slot_holder: list[int],
        *,
        chunk_index: int,
        entity_type: EntityType,
        title: str,
        content: str,
        tags: dict,
        chunk: str,
        abs_start: int,
        abs_end: int,
    ) -> None:
        slot_holder[0] += 1
        collected.append(
            ExtractedEntityCandidate(
                entity_type=entity_type,
                title=_clip(title, 512),
                content=_clip(content, 300),
                confidence_score=self._confidence(chunk_index, slot_holder[0]),
                tags_json=tags,
                evidence_json=self._evidence(chunk, abs_start, abs_end),
            )
        )

    def _process_sentence(
        self,
        sentence: str,
        abs_start: int,
        abs_end: int,
        chunk: str,
        chunk_index: int,
        slot_holder: list[int],
        collected: list[ExtractedEntityCandidate],
        source_filename: str | None,
    ) -> None:
        sent = sentence.strip()
        if not sent:
            return

        def append(
            et: EntityType,
            title: str,
            content: str,
            tags: dict,
            s0: int,
            s1: int,
        ) -> None:
            self._append(
                collected,
                slot_holder,
                chunk_index=chunk_index,
                entity_type=et,
                title=title,
                content=content,
                tags=tags,
                chunk=chunk,
                abs_start=s0,
                abs_end=s1,
            )

        for m in self._URL.finditer(sent):
            url = m.group(0).rstrip(").,;]")
            rel_s = abs_start + m.start()
            rel_e = abs_start + m.end()
            host = urlparse(url).netloc or _clip(url, 40)
            append(
                EntityType.SUPPORTING_FACT,
                host[:512] or "Ссылка",
                _clip(url, 300),
                {"pattern": "url", "source_file": source_filename or ""},
                rel_s,
                rel_e,
            )

        for m in self._EMAIL.finditer(sent):
            rel_s = abs_start + m.start()
            rel_e = abs_start + m.end()
            em = m.group(0)
            append(
                EntityType.SUPPORTING_FACT,
                f"Почта: {em[:80]}",
                em,
                {"pattern": "email"},
                rel_s,
                rel_e,
            )

        remainder = sent
        for m in self._URL.finditer(sent):
            remainder = remainder.replace(m.group(0), " ")
        for m in self._EMAIL.finditer(sent):
            remainder = remainder.replace(m.group(0), " ")
        rem_words = [w for w in re.split(r"\W+", remainder.lower()) if w]
        if len(rem_words) < 2:
            return
        filler_only = {
            "see",
            "and",
            "contact",
            "at",
            "the",
            "a",
            "an",
            "or",
            "to",
            "for",
            "on",
            "in",
            "of",
            "и",
            "или",
            "в",
            "на",
            "по",
            "к",
            "у",
            "о",
            "об",
            "за",
            "из",
            "от",
            "до",
            "для",
            "без",
            "при",
            "это",
            "как",
        }
        if len(rem_words) <= 6 and all(w in filler_only for w in rem_words):
            return

        sem_title = _title_from_sentence(sent, "Формулировка")
        sem_content = _clip(sent, 300)
        base_tags: dict = {"source_file": source_filename or ""}

        if self._REC_START.match(sent):
            append(
                EntityType.RECOMMENDATION,
                sem_title,
                sem_content,
                {**base_tags, "rule": "starter"},
                abs_start,
                abs_end,
            )
        elif self._HYP_START.match(sent):
            append(
                EntityType.HYPOTHESIS,
                sem_title,
                sem_content,
                {**base_tags, "rule": "hypothesis_starter"},
                abs_start,
                abs_end,
            )
        elif self._PROBLEM.search(sent):
            append(
                EntityType.PROBLEM,
                sem_title,
                sem_content,
                {**base_tags, "rule": "problem_signal"},
                abs_start,
                abs_end,
            )
        elif self._RISK.search(sent):
            append(
                EntityType.RISK,
                sem_title,
                sem_content,
                {**base_tags, "rule": "risk_keyword"},
                abs_start,
                abs_end,
            )
        elif self._OPP.search(sent):
            append(
                EntityType.OPPORTUNITY,
                sem_title,
                sem_content,
                {**base_tags, "rule": "opportunity_keyword"},
                abs_start,
                abs_end,
            )
        elif self._INSIGHT.search(sent):
            append(
                EntityType.BEHAVIOR_PATTERN,
                sem_title,
                sem_content,
                {**base_tags, "rule": "user_behavior"},
                abs_start,
                abs_end,
            )
        elif self._NUMBER.search(sent):
            append(
                EntityType.SUPPORTING_FACT,
                sem_title,
                sem_content,
                {**base_tags, "rule": "numeric"},
                abs_start,
                abs_end,
            )
        else:
            append(
                EntityType.SUPPORTING_FACT,
                sem_title,
                sem_content,
                {**base_tags, "rule": "sentence_fallback"},
                abs_start,
                abs_end,
            )

    def extract_from_chunk(
        self,
        *,
        text: str,
        chunk_index: int,
        source_filename: str | None,
    ) -> list[ExtractedEntityCandidate]:
        chunk = (text or "").strip()
        if not chunk:
            return []

        sentences = _split_sentences(chunk)
        slot_holder = [0]
        collected: list[ExtractedEntityCandidate] = []

        for sent, s0, s1 in sentences:
            for piece, p0, p1 in _expand_sentence_fragments(sent, s0, s1):
                self._process_sentence(
                    piece,
                    p0,
                    p1,
                    chunk,
                    chunk_index,
                    slot_holder,
                    collected,
                    source_filename,
                )

        if len(collected) < 3 and len(chunk) >= 30:
            n_seg = min(6, max(3, (len(chunk) + 99) // 100))
            existing_spans = [
                (int(c.evidence_json.get("span_start", 0)), int(c.evidence_json.get("span_end", 0)))
                for c in collected
            ]

            def _overlaps(a: int, b: int) -> bool:
                for x, y in existing_spans:
                    if not (b <= x or a >= y):
                        return True
                return False

            for a, b in _even_segments(chunk, n_seg):
                if len(collected) >= 8:
                    break
                if _overlaps(a, b):
                    continue
                snippet = chunk[a:b].strip()
                if len(snippet) < 12:
                    continue
                self._append(
                    collected,
                    slot_holder,
                    chunk_index=chunk_index,
                    entity_type=EntityType.SUPPORTING_FACT,
                    title=_title_from_sentence(snippet, "Фрагмент"),
                    content=_clip(snippet, 300),
                    tags={
                        "rule": "segment_density",
                        "source_file": source_filename or "",
                    },
                    chunk=chunk,
                    abs_start=a,
                    abs_end=b,
                )

        if not collected:
            self._append(
                collected,
                slot_holder,
                chunk_index=chunk_index,
                entity_type=EntityType.SUPPORTING_FACT,
                title=_title_from_sentence(chunk, "Сводка по фрагменту"),
                content=_clip(chunk, 300),
                tags={
                    "rule": "chunk_fallback",
                    "source_file": source_filename or "",
                },
                chunk=chunk,
                abs_start=0,
                abs_end=len(chunk),
            )

        collected.sort(
            key=lambda c: (
                int(c.evidence_json.get("span_start", 0)),
                int(c.evidence_json.get("span_end", 0)),
                c.entity_type.value,
            )
        )
        if len(collected) > 8:
            collected[:] = collected[:8]
        return collected
