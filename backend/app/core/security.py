"""Security utilities: JWT tokens, password hashing, AES-256-GCM encryption.

Gmail OAuth tokens are encrypted at rest (AES-256-GCM) in PostgreSQL keyed by user_id.
Tokens are never logged.
"""

import base64
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(subject: str, email: str | None = None, expires_delta: timedelta | None = None) -> str:
    to_encode: dict[str, Any] = {"sub": str(subject), "type": "access", "jti": secrets.token_urlsafe(16)}
    if email:
        to_encode["email"] = email
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str, email: str | None = None, version: int = 0) -> str:
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "version": version,
    }
    if email:
        to_encode["email"] = email
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


def generate_random_token() -> str:
    return secrets.token_urlsafe(32)


class TokenEncryption:
    """AES-256-GCM encryption for OAuth tokens at rest."""

    def __init__(self, key_b64: str) -> None:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to exactly 32 bytes")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, token_b64: str) -> str:
        data = base64.b64decode(token_b64)
        nonce, ciphertext = data[:12], data[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
