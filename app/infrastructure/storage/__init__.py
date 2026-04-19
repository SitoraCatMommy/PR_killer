"""Pluggable file storage (local disk today; S3-compatible later)."""

from app.infrastructure.storage.base import FileStorage
from app.infrastructure.storage.local import LocalFileStorage

__all__ = ["FileStorage", "LocalFileStorage"]
