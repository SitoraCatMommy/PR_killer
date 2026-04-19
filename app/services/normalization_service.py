import re
import unicodedata


class NormalizationService:
    """Unicode normalization and light whitespace cleanup for research text."""

    _multi_space = re.compile(r"[ \t]+")
    _blank_lines = re.compile(r"\n{3,}")

    def normalize(self, text: str) -> str:
        t = unicodedata.normalize("NFC", text.strip())
        t = self._multi_space.sub(" ", t)
        t = self._blank_lines.sub("\n\n", t)
        return t
