"""FastAPI application factory and Cloudflare Workers entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from relay.api.router import api_router
from relay.exceptions import (
    AdapterDisabledError,
    LinearError,
    SignatureError,
    ValidationError,
)

logger = logging.getLogger("relay")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        app.state.http = client
        yield


def create_app() -> FastAPI:
    """Build the FastAPI application (usable in tests without Workers)."""
    app = FastAPI(
        title="Relay",
        description="Discord/Slack slash commands → Linear",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SignatureError)
    async def _signature_error(
        _request: Request,
        exc: SignatureError,
    ) -> JSONResponse:
        logger.warning("Signature verification failed: %s", exc)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    @app.exception_handler(AdapterDisabledError)
    async def _adapter_disabled(
        _request: Request,
        exc: AdapterDisabledError,
    ) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ValidationError)
    async def _validation_error(
        _request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(LinearError)
    async def _linear_error(
        _request: Request,
        exc: LinearError,
    ) -> JSONResponse:
        logger.error("Linear error: %s", exc)
        return JSONResponse({"detail": "Linear request failed"}, status_code=502)


app = create_app()

# Cloudflare Python Workers ASGI entrypoint.
# Imported lazily so unit tests do not require the workers SDK.
Default: Any
try:
    from workers import asgi

    Default = asgi.entrypoint(app)
except ImportError:  # pragma: no cover - local pytest without workers SDK
    Default = None
