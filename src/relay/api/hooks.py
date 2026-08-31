"""Chat webhook routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from relay.adapters.base import CreatedIssue, IssueDraft
from relay.adapters.registry import get_adapter
from relay.deps import EnricherDep, LinearClientDep, SettingsDep
from relay.exceptions import AdapterDisabledError, ValidationError

logger = logging.getLogger("relay.api.hooks")

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/{provider}")
async def handle_hook(
    provider: str,
    request: Request,
    settings: SettingsDep,
    linear: LinearClientDep,
    enricher: EnricherDep,
) -> Response:
    adapter = get_adapter(provider)
    if adapter is None or not adapter.enabled(settings):
        raise AdapterDisabledError(f"Adapter '{provider}' is not enabled")

    async def create_issue(draft: IssueDraft) -> CreatedIssue:
        if not draft.title.strip():
            raise ValidationError("Title is required")
        improved = await enricher.enrich(draft)
        return await linear.create_issue(improved)

    return await adapter.handle(request, settings, create_issue=create_issue)
