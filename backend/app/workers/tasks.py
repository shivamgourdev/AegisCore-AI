"""Celery task placeholders.

Long-running jobs (document ingestion, RAG indexing, email sending) are
declared here and registered with the Celery app.
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.ingest_document")
def ingest_document(document_id: str, user_id: str) -> dict:
    """Ingest and index a document (placeholder)."""
    return {"document_id": document_id, "user_id": user_id, "status": "queued"}


@celery_app.task(name="app.workers.tasks.send_email")
def send_email(draft_id: str, user_id: str) -> dict:
    """Send an approved email draft (placeholder)."""
    return {"draft_id": draft_id, "user_id": user_id, "status": "queued"}
