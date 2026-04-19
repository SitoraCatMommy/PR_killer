from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStorage(Protocol):
    """Store arbitrary bytes at a logical path; returns a stable relative key/path string."""

    async def save(self, relative_dir: Path, filename: str, data: bytes) -> str:
        """Persist `data` under base_path / relative_dir / unique_filename. Return stored relative path."""
        ...
