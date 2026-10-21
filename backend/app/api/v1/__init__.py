"""API router registration (v1)."""

from fastapi import APIRouter

from app.api.v1 import auth, uploads, rag

api_router = APIRouter(prefix="")

api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(uploads.router, prefix="/uploads")
api_router.include_router(rag.router, prefix="/rag")
