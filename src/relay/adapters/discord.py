"""Discord Interactions adapter (slash command /issue)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from relay.adapters.base import (
    CreateIssueFn,
    IssueDraft,
    ListProjectsFn,
    Priority,
)
from relay.config import Settings
from relay.crypto import verify_discord_ed25519
from relay.exceptions import SignatureError, ValidationError

logger = logging.getLogger("relay.adapters.discord")

_PING = 1
_APPLICATION_COMMAND = 2
_AUTOCOMPLETE = 4
_CHANNEL_MESSAGE = 4
_AUTOCOMPLETE_RESULT = 8
_EPHEMERAL = 1 << 6

_PRIORITY_BY_NAME: dict[str, Priority] = {
    "none": 0,
    "urgent": 1,
    "high": 2,
    "normal": 3,
    "low": 4,
}


class DiscordAdapter:
    """Handle Discord Interactions webhook."""

    name = "discord"

    def enabled(self, settings: Settings) -> bool:
        return settings.discord_enabled

    async def handle(
        self,
        request: Request,
        settings: Settings,
        *,
        create_issue: CreateIssueFn,
        list_projects: ListProjectsFn,
    ) -> Response:
        body = await request.body()
        signature = request.headers.get("x-signature-ed25519", "")
        timestamp = request.headers.get("x-signature-timestamp", "")
        public_key = settings.discord_public_key
        if not public_key:
            raise SignatureError("Discord public key not configured")

        try:
            verify_discord_ed25519(
                body=body,
                signature_hex=signature,
                timestamp=timestamp,
                public_key_hex=public_key,
            )
        except SignatureError:
            return Response(status_code=401)

        payload: dict[str, Any] = json.loads(body)
        interaction_type = payload.get("type")

        if interaction_type == _PING:
            return JSONResponse({"type": 1})

        if interaction_type == _AUTOCOMPLETE:
            return await self._autocomplete(payload, list_projects)

        if interaction_type != _APPLICATION_COMMAND:
            return JSONResponse(
                {
                    "type": _CHANNEL_MESSAGE,
                    "data": {
                        "content": "Unsupported interaction type.",
                        "flags": _EPHEMERAL,
                    },
                }
            )

        try:
            draft = self._parse_command(payload)
        except ValidationError as exc:
            return JSONResponse(
                {
                    "type": _CHANNEL_MESSAGE,
                    "data": {"content": str(exc), "flags": _EPHEMERAL},
                }
            )

        try:
            issue = await create_issue(draft)
        except Exception:
            logger.exception("Failed to create Linear issue from Discord")
            return JSONResponse(
                {
                    "type": _CHANNEL_MESSAGE,
                    "data": {
                        "content": "Failed to create Linear issue. Try again.",
                        "flags": _EPHEMERAL,
                    },
                }
            )

        extras: list[str] = []
        if draft.project_name:
            extras.append(f"project **{draft.project_name}**")
        if draft.priority is not None and draft.priority != 0:
            labels = {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}
            extras.append(f"priority **{labels.get(draft.priority, draft.priority)}**")
        suffix = f" ({', '.join(extras)})" if extras else ""

        return JSONResponse(
            {
                "type": _CHANNEL_MESSAGE,
                "data": {
                    "content": (
                        f"Created **{issue.identifier}** — {issue.url}{suffix}"
                    ),
                },
            }
        )

    async def _autocomplete(
        self,
        payload: dict[str, Any],
        list_projects: ListProjectsFn,
    ) -> JSONResponse:
        data = payload.get("data") or {}
        focused = ""
        query = ""
        for opt in data.get("options") or []:
            if isinstance(opt, dict) and opt.get("focused"):
                focused = str(opt.get("name") or "")
                query = str(opt.get("value") or "")
                break

        choices: list[dict[str, str]] = []
        if focused == "project":
            try:
                projects = await list_projects(query)
            except Exception:
                logger.exception("Project autocomplete failed")
                projects = []
            choices = [
                {"name": p.name[:100], "value": p.id}
                for p in projects[:25]
            ]

        return JSONResponse(
            {"type": _AUTOCOMPLETE_RESULT, "data": {"choices": choices}}
        )

    def _parse_command(self, payload: dict[str, Any]) -> IssueDraft:
        data = payload.get("data") or {}
        options = {
            opt["name"]: opt.get("value")
            for opt in (data.get("options") or [])
            if isinstance(opt, dict) and "name" in opt
        }
        title = (options.get("title") or "").strip()
        if not title:
            raise ValidationError("Title is required. Usage: `/issue title:...`")

        description = options.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None

        raw_project = options.get("project")
        project_id = (
            raw_project.strip() or None if isinstance(raw_project, str) else None
        )

        priority = _parse_priority(options.get("priority"))

        member = payload.get("member") or {}
        user = member.get("user") or payload.get("user") or {}
        author = user.get("username") or user.get("global_name") or "unknown"
        channel = payload.get("channel_id")

        return IssueDraft(
            title=title,
            description=description,
            source="discord",
            author=str(author),
            channel=str(channel) if channel else None,
            project_id=project_id,
            # Discord autocomplete stores id in value; name is only for display.
            project_name=None,
            priority=priority,
        )


def _parse_priority(raw: Any) -> Priority | None:
    if raw is None:
        return None
    if isinstance(raw, int) and raw in (0, 1, 2, 3, 4):
        return raw  # type: ignore[return-value]
    if isinstance(raw, str):
        key = raw.strip().lower()
        if key in _PRIORITY_BY_NAME:
            return _PRIORITY_BY_NAME[key]
        if key.isdigit() and int(key) in (0, 1, 2, 3, 4):
            return int(key)  # type: ignore[return-value]
    raise ValidationError("Priority must be none, urgent, high, normal, or low")
