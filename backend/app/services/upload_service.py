"""Upload business logic."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".xlsx", ".xls"}


class FileTooLargeError(ValueError):
    """Raised when uploaded file exceeds the size limit."""


# Magic byte signatures for allowed file types
MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".txt": None,  # Text files have no fixed magic bytes; validated by extension + content
    ".md": None,   # Markdown files have no fixed magic bytes
    ".markdown": None,  # Markdown files have no fixed magic bytes
    ".xlsx": b"PK\x03\x04",
    ".xls": b"\xD0\xCF\x11\xE0",
}

CHUNK_SIZE = 8192


def _get_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def _validate_magic_bytes(file_content_start: bytes, extension: str) -> bool:
    """Validate that file content starts with the expected magic bytes for its extension."""
    signature = MAGIC_BYTES.get(extension)
    if signature is None:
        # .txt files: accept if content is decodable as text
        try:
            file_content_start.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                file_content_start.decode("latin-1")
                return True
            except UnicodeDecodeError:
                return False
    return file_content_start.startswith(signature)


def validate_upload(filename: str, content_type: str, file) -> str:
    """Validate an uploaded file. Returns the sanitized extension or raises ValueError.

    Size is enforced by reading the file content and checking its length.
    """
    import traceback as tb_module

    extension = _get_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{extension}' is not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Read file content for size and magic-byte validation
    content = b""
    try:
        if hasattr(file, "file") and file.file is not None:
            file.file.seek(0)
            content = file.file.read()
            file.file.seek(0)
            import sys
            print(f"DEBUG: file.file.read() returned type={type(content).__name__}, value_len={len(content) if content is not None else 'None'}", file=sys.stderr)
        else:
            content = file.read()
            import sys
            print(f"DEBUG: file.read() returned type={type(content).__name__}, len={len(content) if content is not None else 'None'}", file=sys.stderr)
    except Exception as e:
        raise ValueError(f"Unable to read file content: {type(e).__name__}: {e}")

    total_bytes = len(content) if content is not None else 0
    if content is None:
        content = b""

    import sys
    print(f"DEBUG validate_upload: content type={type(content).__name__}, content_len={len(content) if content is not None else 'None'}", file=sys.stderr)

    max_bytes = settings.upload_max_size_mb * 1024 * 1024
    if total_bytes > max_bytes:
        raise FileTooLargeError(f"File size exceeds {settings.upload_max_size_mb} MB limit")

    # Magic-byte validation on the file content
    if not _validate_magic_bytes(content, extension):
        raise ValueError(f"File content does not match extension '{extension}'")

    return extension


def signature_for(extension: str) -> bytes:
    """Return the magic-byte signature for an extension, or empty bytes for .txt."""
    return MAGIC_BYTES.get(extension, b"")


def save_upload(file, user_id: str, extension: str) -> dict:
    """Save an uploaded file to per-user storage. Returns metadata dict.

    Size is enforced during writing as a defense-in-depth check.
    """
    file_id = str(uuid.uuid4())
    user_dir = Path(settings.upload_dir) / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_path = user_dir / f"{file_id}{extension}"

    max_bytes = settings.upload_max_size_mb * 1024 * 1024
    total_bytes = 0

    try:
        # Re-read content for saving (UploadFile may have been consumed by validate_upload)
        if hasattr(file, "file"):
            file.file.seek(0)
            with open(storage_path, "wb") as f:
                while True:
                    chunk = file.file.read(CHUNK_SIZE)
                    if chunk is None or not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        f.close()
                        cleanup_partial_upload(str(storage_path))
                        raise FileTooLargeError(f"File size exceeds {settings.upload_max_size_mb} MB limit")
                    f.write(chunk)
        else:
            content = file.read()
            total_bytes = len(content)
            if total_bytes > max_bytes:
                cleanup_partial_upload(str(storage_path))
                raise FileTooLargeError(f"File size exceeds {settings.upload_max_size_mb} MB limit")
            with open(storage_path, "wb") as f:
                f.write(content)
            file.seek(0)
    except Exception as e:
        # Clean up partial file on error
        cleanup_partial_upload(str(storage_path))
        raise ValueError(f"Failed to save file: {type(e).__name__}: {e}")

    size_bytes = storage_path.stat().st_size
    return {
        "id": file_id,
        "filename": getattr(file, "filename", storage_path.name),
        "content_type": getattr(file, "content_type", "application/octet-stream"),
        "size_bytes": size_bytes,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    }


def cleanup_partial_upload(storage_path: str) -> None:
    """Delete a partial or rejected upload file."""
    try:
        os.remove(storage_path)
    except FileNotFoundError:
        pass
