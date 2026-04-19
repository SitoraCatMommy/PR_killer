"""Split text into overlapping character windows with word/line-aware boundaries."""


from __future__ import annotations


class ChunkingService:
    def __init__(self, *, max_chars: int = 500, overlap_chars: int = 80) -> None:
        self._max_chars = max(1, int(max_chars))
        o = max(0, int(overlap_chars))
        if o >= self._max_chars:
            o = max(0, self._max_chars - 1)
        self._overlap_chars = o

    def chunk_text(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self._max_chars:
            return [text]

        chunks: list[str] = []
        start = 0
        n = len(text)
        max_c = self._max_chars
        ov = self._overlap_chars
        min_break = max(1, max_c * 4 // 10)

        while start < n:
            end = min(n, start + max_c)
            if end < n:
                segment = text[start:end]
                lb = segment.rfind(" ")
                nl = segment.rfind("\n")
                brk = max(lb, nl)
                if brk >= min_break:
                    end = start + brk
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            elif end < n:
                start = min(n, start + max_c)
                continue
            if end >= n:
                break
            next_start = end - ov
            if next_start <= start:
                next_start = start + 1
            while next_start < n and text[next_start] in " \n\t\r":
                next_start += 1
            if next_start >= n:
                break
            if next_start <= start:
                next_start = min(n, start + max_c)
            start = next_start

        return chunks
