from pydantic import BaseModel, Field


class ProcessingTaskQueued(BaseModel):
    task_id: str = Field(..., description="Celery task id")
    status: str = Field(default="queued")
