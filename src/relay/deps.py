"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import Depends, Request

from relay.config import Settings
from relay.enrich import IssueEnricher
from relay.linear.client import LinearClient


def _binding(env: Any, name: str) -> str | None:
    """Read a Worker binding / attribute, returning None if missing or empty."""
    value = getattr(env, name, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_settings(request: Request) -> Settings:
    """Resolve settings from Worker env bindings, else load `.env`.

    Must stay request-scoped — never call this at module import so secrets
    are not baked into the Cloudflare memory snapshot on deploy.
    """
    env = request.scope.get("env")
    if env is not None and _binding(env, "LINEAR_API_KEY"):
        data: dict[str, Any] = {
            "linear_api_key": _binding(env, "LINEAR_API_KEY"),
            "linear_team_id": _binding(env, "LINEAR_TEAM_ID"),
            "discord_public_key": _binding(env, "DISCORD_PUBLIC_KEY"),
            "slack_signing_secret": _binding(env, "SLACK_SIGNING_SECRET"),
            "groq_api_key": _binding(env, "GROQ_API_KEY"),
        }
        model = _binding(env, "GROQ_MODEL")
        if model:
            data["groq_model"] = model
        return Settings.model_validate(data)
    # Loads from process env / `.env` (local scripts & tests).
    return Settings()  # type: ignore[call-arg]


def get_http_client(request: Request) -> httpx.AsyncClient:
    client = getattr(request.app.state, "http", None)
    if not isinstance(client, httpx.AsyncClient):
        msg = "HTTP client not initialized; check app lifespan"
        raise RuntimeError(msg)
    return client


def get_linear_client(
    settings: Annotated[Settings, Depends(get_settings)],
    http: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> LinearClient:
    return LinearClient(http=http, settings=settings)


def get_issue_enricher(
    settings: Annotated[Settings, Depends(get_settings)],
    http: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> IssueEnricher:
    return IssueEnricher(http=http, settings=settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]
LinearClientDep = Annotated[LinearClient, Depends(get_linear_client)]
EnricherDep = Annotated[IssueEnricher, Depends(get_issue_enricher)]
