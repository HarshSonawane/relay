"""Discord Interactions adapter (slash command /issue)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from relay.adapters.base import CreateIssueFn, IssueDraft
from relay.config import Settings
from relay.crypto import verify_discord_ed25519
from relay.exceptions import SignatureError, ValidationError

logger = logging.getLogger("relay.adapters.discord")

_PING = 1
_APPLICATION_COMMAND = 2
_CHANNEL_MESSAGE = 4
_EPHEMERAL = 1 << 6


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
    ) -> Response:
        body = await request.body()
        signature = request.headers.get("x-signature-ed25519", "")
        timestamp = request.headers.get("x-signature-timestamp", "")
        public_key = settings.discord_public_key
        if not public_key:
            raise SignatureError("Discord public key not configured")

        # Discord expects HTTP 401 with empty body on bad signatures during
        # endpoint validation — return Response(401) rather than JSON detail.
        try:
            await verify_discord_ed25519(
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

        return JSONResponse(
            {
                "type": _CHANNEL_MESSAGE,
                "data": {
                    "content": f"Created **{issue.identifier}** — {issue.url}",
                },
            }
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
        )
