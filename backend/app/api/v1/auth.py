"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.core.security import decode_token
from app.dependencies import get_current_active_user
from app.schemas.auth import Token, UserCreate, UserLogin, UserOut
from app.services.auth_service import (
    authenticate_user,
    create_tokens,
    get_user_from_refresh_token,
    register_user,
    rotate_refresh_token,
)

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/register", response_model=UserOut, status_code=201)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    try:
        return register_user(db, user_in.email, user_in.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and return access + refresh tokens."""
    user = authenticate_user(db, user_in.email, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return create_tokens(user)


@router.post("/refresh", response_model=Token)
def refresh(token: str, db: Session = Depends(get_db)):
    """Obtain a new access token from a valid refresh token.

    The refresh token's embedded version is compared against the user's current
    refresh_token_version. A mismatch means the token has been rotated (revoked)
    and is rejected. On success, the version is incremented, invalidating this
    refresh token and all previously issued ones.
    """
    try:
        user = get_user_from_refresh_token(token, db)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    rotate_refresh_token(user, db)
    return create_tokens(user)


@router.get("/me", response_model=UserOut)
def get_me(current_user=Depends(get_current_active_user)):
    """Get the current authenticated user's profile."""
    return current_user
