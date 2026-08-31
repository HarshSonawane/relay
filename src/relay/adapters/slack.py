"""Slack slash-command adapter (/issue)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from fastapi import Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from relay.adapters.base import CreateIssueFn, IssueDraft
from relay.config import Settings
from relay.crypto import verify_slack_signature
from relay.exceptions import SignatureError, ValidationError

logger = logging.getLogger("relay.adapters.slack")


class SlackAdapter:
    """Handle Slack slash-command webhook."""

    name = "slack"

    def enabled(self, settings: Settings) -> bool:
        return settings.slack_enabled

    async def handle(
        self,
        request: Request,
        settings: Settings,
        *,
        create_issue: CreateIssueFn,
    ) -> Response:
        body = await request.body()
        signature = request.headers.get("x-slack-signature", "")
        timestamp = request.headers.get("x-slack-request-timestamp", "")
        secret = settings.slack_signing_secret
        if secret is None:
            raise SignatureError("Slack signing secret not configured")

        verify_slack_signature(
            body=body,
            signature=signature,
            timestamp=timestamp,
            signing_secret=secret.get_secret_value(),
        )

        form = _parse_form(body)

        # URL verification challenge (if ever pointed at Events API)
        if form.get("type") == ["url_verification"]:
            challenge = (form.get("challenge") or [""])[0]
            return PlainTextResponse(challenge)

        try:
            draft = self._parse_command(form)
        except ValidationError as exc:
            return JSONResponse(
                {
                    "response_type": "ephemeral",
                    "text": str(exc),
                }
            )

        try:
            issue = await create_issue(draft)
        except Exception:
            logger.exception("Failed to create Linear issue from Slack")
            return JSONResponse(
                {
                    "response_type": "ephemeral",
                    "text": "Failed to create Linear issue. Try again.",
                }
            )

        return JSONResponse(
            {
                "response_type": "in_channel",
                "text": f"Created *{issue.identifier}* — {issue.url}",
            }
        )

    def _parse_command(self, form: dict[str, list[str]]) -> IssueDraft:
        text = (form.get("text") or [""])[0].strip()
        if not text:
            raise ValidationError(
                "Title is required. Usage: `/issue Fix login` "
                "or `/issue Fix login | users cannot SSO`"
            )

        if "|" in text:
            title_part, _, desc_part = text.partition("|")
            title = title_part.strip()
            description = desc_part.strip() or None
        else:
            title = text
            description = None

        if not title:
            raise ValidationError("Title is required.")

        author = (form.get("user_name") or ["unknown"])[0]
        channel_vals = form.get("channel_name") or form.get("channel_id") or []
        channel = channel_vals[0] if channel_vals else None

        return IssueDraft(
            title=title,
            description=description,
            source="slack",
            author=author,
            channel=channel,
        )


def _parse_form(body: bytes) -> dict[str, list[str]]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
    parsed: dict[str, Any] = parse_qs(text, keep_blank_values=True)
    return {k: [str(v) for v in vals] for k, vals in parsed.items()}
