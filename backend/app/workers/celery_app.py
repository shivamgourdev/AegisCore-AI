"""Celery app initialization."""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "aegis_worker",
    broker=settings.redis_url if hasattr(settings, "redis_url") else "redis://localhost:6379/0",
    backend=settings.redis_url if hasattr(settings, "redis_url") else "redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
