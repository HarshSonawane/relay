"""Slack slash-command adapter (/issue)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs

from fastapi import Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from relay.adapters.base import (
    CreateIssueFn,
    IssueDraft,
    LinearProject,
    ListProjectsFn,
    Priority,
)
from relay.config import Settings
from relay.crypto import verify_slack_signature
from relay.exceptions import SignatureError, ValidationError

logger = logging.getLogger("relay.adapters.slack")

_PRIORITY_BY_NAME: dict[str, Priority] = {
    "none": 0,
    "urgent": 1,
    "high": 2,
    "normal": 3,
    "medium": 3,
    "low": 4,
}


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
        list_projects: ListProjectsFn,
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

        if draft.project_name and not draft.project_id:
            try:
                match = await _resolve_project(list_projects, draft.project_name)
            except Exception:
                logger.exception("Project resolve failed")
                match = None
            if match is None:
                return JSONResponse(
                    {
                        "response_type": "ephemeral",
                        "text": (
                            f"No Linear project matching `{draft.project_name}`. "
                            "Try a closer name."
                        ),
                    }
                )
            draft = draft.model_copy(
                update={"project_id": match.id, "project_name": match.name}
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

        extras: list[str] = []
        if draft.project_name:
            extras.append(f"project *{draft.project_name}*")
        if draft.priority:
            labels = {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}
            extras.append(f"priority *{labels.get(draft.priority, draft.priority)}*")
        suffix = f" ({', '.join(extras)})" if extras else ""

        return JSONResponse(
            {
                "response_type": "in_channel",
                "text": f"Created *{issue.identifier}* — {issue.url}{suffix}",
            }
        )

    def _parse_command(self, form: dict[str, list[str]]) -> IssueDraft:
        text = (form.get("text") or [""])[0].strip()
        if not text:
            raise ValidationError(
                "Usage: `/issue Fix login` or "
                "`/issue Fix login | desc | project:Mobile | priority:high`"
            )

        parts = [p.strip() for p in text.split("|")]
        title = parts[0]
        description: str | None = None
        project_name: str | None = None
        priority: Priority | None = None

        for part in parts[1:]:
            keyed = _parse_keyed(part)
            if keyed:
                key, value = keyed
                if key in {"project", "proj", "p"}:
                    project_name = value
                elif key in {"priority", "pri"}:
                    priority = _parse_priority(value)
                else:
                    raise ValidationError(f"Unknown field `{key}`")
            elif description is None:
                description = part or None
            else:
                description = f"{description}\n{part}"

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
            project_name=project_name,
            priority=priority,
        )


def _parse_keyed(part: str) -> tuple[str, str] | None:
    match = re.match(r"^([a-zA-Z]+)\s*:\s*(.+)$", part.strip())
    if not match:
        return None
    return match.group(1).lower(), match.group(2).strip()


def _parse_priority(raw: str) -> Priority:
    key = raw.strip().lower()
    if key in _PRIORITY_BY_NAME:
        return _PRIORITY_BY_NAME[key]
    if key.isdigit() and int(key) in (0, 1, 2, 3, 4):
        return int(key)  # type: ignore[return-value]
    raise ValidationError(
        "Priority must be none, urgent, high, normal, or low"
    )


async def _resolve_project(
    list_projects: ListProjectsFn,
    name: str,
) -> LinearProject | None:
    projects = await list_projects(name)
    if not projects:
        return None
    lowered = name.strip().lower()
    for project in projects:
        if project.name.lower() == lowered:
            return project
    return projects[0]


def _parse_form(body: bytes) -> dict[str, list[str]]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
    parsed: dict[str, Any] = parse_qs(text, keep_blank_values=True)
    return {k: [str(v) for v in vals] for k, vals in parsed.items()}
