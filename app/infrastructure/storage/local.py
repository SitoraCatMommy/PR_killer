import asyncio
import uuid
from pathlib import Path

from app.infrastructure.settings import Settings, get_settings


def safe_upload_filename(filename: str | None, default: str = "upload.bin") -> str:
    candidate = (filename or "").replace("\\", "/").split("/")[-1]
    candidate = candidate.replace("\x00", "").replace("..", "_").strip()
    if not candidate or candidate in {".", "_"}:
        return default
    return candidate


class LocalFileStorage:
    """Filesystem-backed storage under a configurable root (e.g. `/data/uploads`)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._root = Path(self._settings.upload_storage_path)

    async def save(self, relative_dir: Path, filename: str, data: bytes) -> str:
        safe_name = safe_upload_filename(filename)
        unique = f"{uuid.uuid4().hex}_{safe_name}"
        target_dir = self._root / relative_dir
        await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)
        full_path = target_dir / unique
        await asyncio.to_thread(full_path.write_bytes, data)
        try:
            return str(full_path.relative_to(self._root))
        except ValueError:
            return str(full_path)
