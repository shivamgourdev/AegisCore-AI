"""Celery app configuration (long-running jobs)."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "aegis_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1,
)
