"""Pydantic schemas for file uploads."""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str
    user_id: str


class FileValidationError(BaseModel):
    detail: str
