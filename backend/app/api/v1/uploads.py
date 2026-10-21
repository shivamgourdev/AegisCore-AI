"""File upload routes."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
from app.dependencies import get_current_active_user
from app.schemas.upload import UploadResponse
from app.services.upload_service import (
    cleanup_partial_upload,
    FileTooLargeError,
    save_upload,
    validate_upload,
)

router = APIRouter()


@router.post("", response_model=UploadResponse, status_code=201)
def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_active_user),
):
    """Upload a file with validation (size, MIME, magic bytes)."""
    extension = None
    storage_path = None
    try:
        extension = validate_upload(file.filename, file.content_type, file)
        result = save_upload(file, str(current_user.id), extension)
        storage_path = str(
            Path(settings.upload_dir) / str(current_user.id) / f"{result['id']}{extension}"
        )
        return UploadResponse(
            id=result["id"],
            filename=result["filename"],
            content_type=result["content_type"],
            size_bytes=result["size_bytes"],
            uploaded_at=result["uploaded_at"],
            user_id=result["user_id"],
        )
    except FileTooLargeError as e:
        if storage_path:
            cleanup_partial_upload(storage_path)
        raise HTTPException(status_code=413, detail=str(e))
    except ValueError as e:
        if storage_path:
            cleanup_partial_upload(storage_path)
        raise HTTPException(status_code=415, detail=str(e))
    except Exception:
        if storage_path:
            cleanup_partial_upload(storage_path)
        raise HTTPException(status_code=500, detail="Upload failed")


@router.get("")
def list_uploads(current_user=Depends(get_current_active_user)):
    """List the current user's uploads."""
    user_dir = Path(settings.upload_dir) / str(current_user.id)
    if not user_dir.exists():
        return []
    uploads = []
    for p in user_dir.iterdir():
        if p.is_file():
            uploads.append(
                {
                    "id": p.stem,
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                }
            )
    return uploads
