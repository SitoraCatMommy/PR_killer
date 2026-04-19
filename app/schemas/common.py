from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    app: str
    environment: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str | dict[str, Any] | list[Any]
