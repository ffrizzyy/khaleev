"""API routers, mounted under ``/api`` (T09)."""

from __future__ import annotations

from fastapi import APIRouter

from khaleev.api.routes import ask, config, documents

api_router = APIRouter(prefix="/api")
api_router.include_router(documents.router)
api_router.include_router(ask.router)
api_router.include_router(config.router)

__all__ = ["api_router"]
