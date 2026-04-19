from celery import Celery

from app.infrastructure.settings import get_settings

settings = get_settings()

celery_app = Celery(
    settings.app_name,
    broker=str(settings.celery_broker_url),
    backend=str(settings.celery_result_backend),
    include=[
        "app.workers.tasks.pipeline",
        "app.workers.tasks.research_processing",
        "app.workers.tasks.research_extraction",
        "app.workers.tasks.research_aggregate",
        "app.workers.tasks.research_report",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=60 * 30,
    worker_prefetch_multiplier=1,
)
