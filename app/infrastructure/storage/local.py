import uuid
from pathlib import Path

from app.infrastructure.settings import Settings, get_settings


class LocalFileStorage:
    """Filesystem-backed storage under a configurable root (e.g. `/data/uploads`)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._root = Path(self._settings.upload_storage_path)

    async def save(self, relative_dir: Path, filename: str, data: bytes) -> str:
        safe_name = filename.replace("..", "_").strip() or "upload.bin"
        unique = f"{uuid.uuid4().hex}_{safe_name}"
        target_dir = self._root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        full_path = target_dir / unique
        full_path.write_bytes(data)
        try:
            return str(full_path.relative_to(self._root))
        except ValueError:
            return str(full_path)
