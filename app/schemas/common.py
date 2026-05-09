from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    app: str
    environment: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str | dict[str, Any] | list[Any]


class BulkUploadItemResult(BaseModel):
    filename: str
    status: str
    id: UUID | None = None
    source_kind: str | None = None
    task_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class BulkUploadResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BulkUploadItemResult]
