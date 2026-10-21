"""Authentication unit and integration tests."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token, get_password_hash, verify_password
from app.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.auth import TokenData, UserCreate, UserLogin, UserOut


def test_password_hashing(db: Session):
    """Password hashing produces a different hash each time and verifies correctly."""
    hashed = get_password_hash("secret123")
    assert hashed != "secret123"
    assert hashed.startswith("$2b$")
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_access_token_has_access_type(db: Session):
    """Access token payload contains type='access'."""
    from app.services.auth_service import create_tokens, get_user_by_id, register_user

    user = register_user(db, "tokentest@example.com", "securepass123")
    tokens = create_tokens(user)
    payload = decode_token(tokens["access_token"])
    assert payload.get("type") == "access"
    assert payload.get("sub") == user.id


def test_refresh_token_has_refresh_type(db: Session):
    """Refresh token payload contains type='refresh'."""
    from app.services.auth_service import create_tokens, register_user

    user = register_user(db, "refreshtest@example.com", "securepass123")
    tokens = create_tokens(user)
    payload = decode_token(tokens["refresh_token"])
    assert payload.get("type") == "refresh"


def test_user_out_excludes_password_hash(db: Session):
    """UserOut schema never includes password_hash."""
    from app.services.auth_service import register_user

    user = register_user(db, "nohash@example.com", "securepass123")
    out = UserOut.model_validate(user)
    assert not hasattr(out, "password_hash")
    assert out.email == "nohash@example.com"


def test_get_user_by_id(db: Session):
    """get_user_by_id retrieves the correct user."""
    from app.services.auth_service import register_user

    user = register_user(db, "getbyid@example.com", "securepass123")
    fetched = User.query.filter_by(email="getbyid@example.com").first() if False else None
    # Use service function instead
    from app.services.auth_service import get_user_by_id as svc_get

    fetched = svc_get(db, user.id)
    assert fetched is not None
    assert fetched.email == "getbyid@example.com"


def test_register_then_login_returns_tokens(client: TestClient):
    """Register a user, then log in and receive access + refresh tokens."""
    reg = client.post("/api/v1/auth/register", json={"email": "reglogin@example.com", "password": "securepass123"})
    assert reg.status_code == 201
    assert reg.json()["email"] == "reglogin@example.com"
    assert "id" in reg.json()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "reglogin@example.com", "password": "securepass123"},
    )
    assert login.status_code == 200
    body = login.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_invalid_credentials_401(client: TestClient):
    """Login with wrong password returns 401."""
    client.post(
        "/api/v1/auth/register",
        json={"email": "badpass@example.com", "password": "securepass123"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "badpass@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_register_duplicate_email_400(client: TestClient):
    """Registering the same email twice returns 400."""
    client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "securepass123"},
    )
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 400


def test_refresh_token_issues_new_access(client: TestClient, db: Session):
    """Refresh endpoint issues a new access token from a valid refresh token."""
    from app.services.auth_service import authenticate_user, create_tokens, register_user

    user = register_user(db, "refreshe2e@example.com", "securepass123")
    tokens = create_tokens(user)

    resp = client.post("/api/v1/auth/refresh", params={"token": tokens["refresh_token"]})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_refresh_token_with_access_token_401(client: TestClient, db: Session):
    """Using an access token at the refresh endpoint returns 401."""
    from app.services.auth_service import authenticate_user, create_tokens, register_user

    user = register_user(db, "mixedtoken@example.com", "securepass123")
    tokens = create_tokens(user)

    resp = client.post("/api/v1/auth/refresh", params={"token": tokens["access_token"]})
    assert resp.status_code == 401


def test_me_endpoint_requires_auth(client: TestClient):
    """GET /me without a token returns 401."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_endpoint_returns_profile(client: TestClient, db: Session):
    """GET /me with a valid access token returns the user profile (no password_hash)."""
    from app.services.auth_service import authenticate_user, create_tokens, register_user

    user = register_user(db, "meprofile@example.com", "securepass123")
    tokens = create_tokens(user)

    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "meprofile@example.com"
    assert "password_hash" not in body
    assert "id" in body


def test_refresh_token_rotation_invalidates_old_token(client: TestClient, db: Session):
    """After refresh, the old refresh token is rejected (version mismatch)."""
    from app.services.auth_service import create_tokens, register_user, rotate_refresh_token

    user = register_user(db, "rotate@example.com", "securepass123")
    tokens = create_tokens(user)

    # First refresh succeeds and rotates the version
    resp1 = client.post(
        "/api/v1/auth/refresh", params={"token": tokens["refresh_token"]}
    )
    assert resp1.status_code == 200

    # The original refresh token should now be rejected (version incremented)
    resp2 = client.post(
        "/api/v1/auth/refresh", params={"token": tokens["refresh_token"]}
    )
    assert resp2.status_code == 401


def test_refresh_token_with_wrong_version_401(db: Session):
    """A refresh token with a stale version is rejected."""
    from app.core.security import create_refresh_token
    from app.services.auth_service import register_user

    user = register_user(db, "version@example.com", "securepass123")
    # Create a refresh token with an old version (0), then increment user's version
    user.refresh_token_version = 5
    db.commit()

    old_token = create_refresh_token(subject=str(user.id), email=user.email, version=0)
    from app.services.auth_service import get_user_from_refresh_token

    with pytest.raises(ValueError, match="Refresh token has been revoked"):
        get_user_from_refresh_token(old_token, db)


def test_access_token_used_as_refresh_401(client: TestClient, db: Session):
    """Using an access token at the refresh endpoint returns 401 (wrong type)."""
    from app.services.auth_service import create_tokens, register_user

    user = register_user(db, "access_as_refresh@example.com", "securepass123")
    tokens = create_tokens(user)

    resp = client.post("/api/v1/auth/refresh", params={"token": tokens["access_token"]})
    assert resp.status_code == 401


def test_refresh_token_used_as_access_401(client: TestClient, db: Session):
    """Using a refresh token at an access-token endpoint returns 401 (wrong type)."""
    from app.services.auth_service import create_tokens, register_user

    user = register_user(db, "refresh_as_access@example.com", "securepass123")
    tokens = create_tokens(user)

    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert resp.status_code == 401


def test_expired_access_token_rejected(db: Session):
    """An access token with a past expiry is rejected."""
    from app.core.security import create_access_token
    from app.services.auth_service import get_current_user_from_token, register_user

    user = register_user(db, "expired@example.com", "securepass123")
    expired_token = create_access_token(
        subject=str(user.id), email=user.email, expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(ValueError):
        get_current_user_from_token(expired_token, db)


def test_malformed_token_rejected(db: Session):
    """A non-JWT string is rejected as an access token."""
    from app.services.auth_service import get_current_user_from_token

    with pytest.raises(ValueError):
        get_current_user_from_token("not-a-jwt-token", db)


def test_wrong_secret_token_rejected(db: Session):
    """A token signed with a different secret key is rejected."""
    from app.core.security import decode_token
    from app.services.auth_service import register_user

    user = register_user(db, "wrongsecret@example.com", "securepass123")
    wrong_secret = "totally-different-secret-key"
    forged_token = jwt.encode(
        {"sub": str(user.id), "type": "access"}, wrong_secret, algorithm="HS256"
    )
    with pytest.raises(Exception):
        decode_token(forged_token)


def test_inactive_user_cannot_authenticate(db: Session):
    """An inactive user cannot log in."""
    from app.services.auth_service import authenticate_user, register_user

    user = register_user(db, "inactive@example.com", "securepass123")
    user.is_active = False
    db.commit()

    result = authenticate_user(db, "inactive@example.com", "securepass123")
    assert result is None


def test_inactive_user_cannot_refresh(db: Session):
    """An inactive user cannot use a refresh token."""
    from app.core.security import create_refresh_token
    from app.services.auth_service import get_user_from_refresh_token, register_user

    user = register_user(db, "inactive-refresh@example.com", "securepass123")
    user.is_active = False
    db.commit()

    token = create_refresh_token(subject=str(user.id), email=user.email, version=0)
    with pytest.raises(ValueError, match="User not found or inactive"):
        get_user_from_refresh_token(token, db)


def test_production_rejects_insecure_secret_key():
    """Production mode rejects the default insecure SECRET_KEY."""
    from app.core.config import Settings

    with pytest.raises(ValueError, match="secret_key must not use the insecure default"):
        Settings(
            app_env="production",
            secret_key="change-me-in-production",
            encryption_key="change-me-32-byte-base64-key",
            database_url="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db",
            redis_url="redis://localhost:6379/0",
        )


def test_production_rejects_insecure_encryption_key():
    """Production mode rejects the default insecure ENCRYPTION_KEY."""
    from app.core.config import Settings

    with pytest.raises(ValueError, match="encryption_key must not use the insecure default"):
        Settings(
            app_env="production",
            secret_key="a-very-secure-secret-key-that-is-not-default",
            encryption_key="change-me-32-byte-base64-key",
            database_url="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db",
            redis_url="redis://localhost:6379/0",
        )


def test_production_accepts_secure_secrets():
    """Production mode accepts non-default secrets."""
    from app.core.config import Settings

    s = Settings(
        app_env="production",
        secret_key="a-very-secure-secret-key-that-is-not-default",
        encryption_key="a-very-secure-encryption-key-that-is-not-default",
        database_url="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db",
        redis_url="redis://localhost:6379/0",
    )
    assert s.rate_limiting_enabled is True


def test_development_allows_insecure_defaults():
    """Development mode allows the insecure default secrets."""
    from app.core.config import Settings

    s = Settings(
        app_env="development",
        secret_key="change-me-in-production",
        encryption_key="change-me-32-byte-base64-key",
        database_url="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db",
        redis_url="redis://localhost:6379/0",
    )
    assert s.rate_limiting_enabled is False


def test_development_rate_limiting_disabled_by_default():
    """Development mode has rate limiting disabled by default."""
    from app.core.config import Settings

    s = Settings(
        app_env="development",
        secret_key="change-me-in-production",
        encryption_key="change-me-32-byte-base64-key",
        database_url="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db",
        redis_url="redis://localhost:6379/0",
    )
    assert s.enable_rate_limiting is False
    assert s.rate_limiting_enabled is False


def test_development_rate_limiting_can_be_enabled():
    """Development mode can opt into rate limiting."""
    from app.core.config import Settings

    s = Settings(
        app_env="development",
        secret_key="change-me-in-production",
        encryption_key="change-me-32-byte-base64-key",
        database_url="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db",
        redis_url="redis://localhost:6379/0",
        enable_rate_limiting=True,
    )
    assert s.rate_limiting_enabled is True
