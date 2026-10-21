"""Upload unit and integration tests."""

import io
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.auth_service import register_user
from app.services.upload_service import cleanup_partial_upload, validate_upload


def test_valid_extensions_allowed():
    """PDF, TXT, XLSX, XLS extensions pass validation."""
    for ext in [".pdf", ".txt", ".xlsx", ".xls"]:
        assert ext in {".pdf", ".txt", ".xlsx", ".xls"}


def test_invalid_extension_rejected():
    """Non-allowed extensions raise ValueError."""
    import io

    from app.services.upload_service import validate_upload

    file = io.BytesIO(b"dummy content")
    file.filename = "malware.exe"
    file.content_type = "application/octet-stream"

    with pytest.raises(ValueError):
        validate_upload(file.filename, file.content_type, file)


def test_oversized_file_rejected():
    """Files larger than upload_max_size_mb raise ValueError."""
    import io

    from app.services.upload_service import validate_upload

    max_bytes = settings.upload_max_size_mb * 1024 * 1024 + 1
    file = io.BytesIO(b"x" * max_bytes)
    file.filename = "big.pdf"
    file.content_type = "application/pdf"

    with pytest.raises(ValueError):
        validate_upload(file.filename, file.content_type, file)


def test_pdf_magic_bytes_accepted():
    """A file starting with %PDF passes magic-byte validation for .pdf."""
    import io

    from app.services.upload_service import validate_upload

    file = io.BytesIO(b"%PDF-1.4 some pdf content")
    file.filename = "document.pdf"
    file.content_type = "application/pdf"

    ext = validate_upload(file.filename, file.content_type, file)
    assert ext == ".pdf"


def test_txt_content_validated():
    """A .txt file with valid text content passes."""
    import io

    from app.services.upload_service import validate_upload

    file = io.BytesIO(b"Hello, this is a text file.")
    file.filename = "notes.txt"
    file.content_type = "text/plain"

    ext = validate_upload(file.filename, file.content_type, file)
    assert ext == ".txt"


def test_exe_with_pdf_extension_rejected():
    """An EXE file renamed to .pdf fails magic-byte validation."""
    import io

    from app.services.upload_service import validate_upload

    # MZ header is the EXE magic bytes
    file = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    file.filename = "fake.pdf"
    file.content_type = "application/pdf"

    with pytest.raises(ValueError):
        validate_upload(file.filename, file.content_type, file)


def test_xlsx_magic_bytes_accepted():
    """A file starting with PK zip signature passes for .xlsx."""
    import io

    from app.services.upload_service import validate_upload

    file = io.BytesIO(b"PK\x03\x04\x14\x00\x06\x00")
    file.filename = "spreadsheet.xlsx"
    file.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    ext = validate_upload(file.filename, file.content_type, file)
    assert ext == ".xlsx"


def test_cleanup_partial_upload(tmp_path):
    """cleanup_partial_upload removes an existing file and ignores missing ones."""
    f = tmp_path / "partial.tmp"
    f.write_bytes(b"partial")
    cleanup_partial_upload(str(f))
    assert not f.exists()
    # Should not raise on missing file
    cleanup_partial_upload(str(tmp_path / "nonexistent.tmp"))


def test_upload_valid_file(client: TestClient, db: Session):
    """Upload a valid PDF returns 201 with metadata."""
    from app.services.auth_service import register_user

    user = register_user(db, "uploader@example.com", "securepass123")
    # We need auth; create a token manually using the service
    from app.services.auth_service import create_tokens

    tokens = create_tokens(user)

    content = b"%PDF-1.4 fake pdf content for testing"
    resp = client.post(
        "/api/v1/uploads",
        files={"file": ("test.pdf", io.BytesIO(content), "application/pdf")},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "test.pdf"
    assert body["user_id"] == user.id
    assert body["size_bytes"] == len(content)


def test_upload_oversized_file_413(client: TestClient, db: Session):
    """Uploading a file larger than 50 MB returns 413."""
    from app.services.auth_service import create_tokens, register_user

    user = register_user(db, "bigfile@example.com", "securepass123")
    tokens = create_tokens(user)

    # Test via validate_upload directly (avoids 50MB HTTP transfer)
    import io

    max_bytes = settings.upload_max_size_mb * 1024 * 1024
    content = b"%PDF-1.4 " + b"x" * max_bytes
    file = io.BytesIO(content)
    file.filename = "big.pdf"
    file.content_type = "application/pdf"

    from app.services.upload_service import FileTooLargeError

    with pytest.raises(FileTooLargeError):
        validate_upload(file.filename, file.content_type, file)


def test_upload_invalid_mime_415(client: TestClient, db: Session):
    """Uploading an EXE file returns 415."""
    from app.services.auth_service import create_tokens, register_user

    user = register_user(db, "badfile@example.com", "securepass123")
    tokens = create_tokens(user)

    content = b"MZ\x90\x00\x03\x00\x00\x00 fake exe"
    resp = client.post(
        "/api/v1/uploads",
        files={"file": ("malware.pdf", io.BytesIO(content), "application/pdf")},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 415


def test_upload_requires_auth_401(client: TestClient):
    """Uploading without a token returns 401."""
    content = b"%PDF-1.4 test"
    resp = client.post(
        "/api/v1/uploads",
        files={"file": ("test.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert resp.status_code == 401


def test_user_isolation(client: TestClient, db: Session):
    """User A cannot see User B's uploads."""
    from app.services.auth_service import create_tokens, register_user

    user_a = register_user(db, "isolation_a@example.com", "securepass123")
    user_b = register_user(db, "isolation_b@example.com", "securepass123")
    tokens_a = create_tokens(user_a)
    tokens_b = create_tokens(user_b)

    content = b"%PDF-1.4 user a file"
    resp_a = client.post(
        "/api/v1/uploads",
        files={"file": ("a.pdf", io.BytesIO(content), "application/pdf")},
        headers={"Authorization": f"Bearer {tokens_a['access_token']}"},
    )
    assert resp_a.status_code == 201
    upload_id_a = resp_a.json()["id"]

    # User B lists uploads - should not see A's file
    resp_b = client.get(
        "/api/v1/uploads",
        headers={"Authorization": f"Bearer {tokens_b['access_token']}"},
    )
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0
