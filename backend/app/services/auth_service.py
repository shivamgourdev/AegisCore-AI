"""Authentication business logic."""

import uuid
from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import UserOut


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def register_user(db: Session, email: str, password: str) -> User:
    """Register a new user. Raises ValueError if email already exists. Returns the User model."""
    if get_user_by_email(db, email):
        raise ValueError("Email already registered")
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=get_password_hash(password),
        refresh_token_version=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Verify credentials and return the user, or None. Inactive users cannot authenticate."""
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def create_tokens(user: User) -> dict[str, Any]:
    """Create access and refresh token pair for a user.

    The refresh token includes the user's current refresh_token_version so that
    rotation can detect and reject stale (already-used) refresh tokens.
    """
    access_token = create_access_token(subject=str(user.id), email=user.email)
    refresh_token = create_refresh_token(
        subject=str(user.id), email=user.email, version=user.refresh_token_version
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def rotate_refresh_token(user: User, db: Session) -> None:
    """Increment the user's refresh_token_version, invalidating all previously issued refresh tokens."""
    user.refresh_token_version += 1
    db.commit()
    db.refresh(user)


def get_current_user_from_token(token: str, db: Session) -> User:
    """Decode a JWT access token and return the associated user."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise ValueError("Invalid token")
    if payload.get("type") != "access":
        raise ValueError("Invalid token type")
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Invalid token")
    user = get_user_by_id(db, str(user_id))
    if not user or not user.is_active:
        raise ValueError("User not found or inactive")
    return user


def get_user_from_refresh_token(token: str, db: Session) -> User:
    """Decode a JWT refresh token and return the associated user.

    The token's embedded version is compared against the user's current
    refresh_token_version. A mismatch means the refresh token has been
    rotated (revoked) and must be rejected.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        raise ValueError("Invalid token")
    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type")
    user_id = payload.get("sub")
    token_version = payload.get("version")
    if not user_id:
        raise ValueError("Invalid token")
    user = get_user_by_id(db, str(user_id))
    if not user or not user.is_active:
        raise ValueError("User not found or inactive")
    if token_version != user.refresh_token_version:
        raise ValueError("Refresh token has been revoked (version mismatch)")
    return user
