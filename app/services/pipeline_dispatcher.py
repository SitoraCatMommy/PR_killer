"""Enqueue legacy Celery material pipeline tasks (separate from domain ingestion)."""

from uuid import UUID

from app.infrastructure.celery_app import celery_app


class MaterialPipelineDispatcher:
    @staticmethod
    def enqueue_material_pipeline(material_id: UUID) -> str:
        task = celery_app.send_task(
            "app.workers.tasks.pipeline.process_material_pipeline",
            args=[str(material_id)],
        )
        return str(task.id)

    @staticmethod
    def enqueue_dashboard_refresh() -> str:
        task = celery_app.send_task("app.workers.tasks.pipeline.recompute_dashboard_aggregates")
        return str(task.id)
