"""Top-level API router."""

from __future__ import annotations

from fastapi import APIRouter

from relay.api import health, hooks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(hooks.router)
