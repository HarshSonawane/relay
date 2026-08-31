"""Shared adapter models and protocol."""

from __future__ import annotations

from typing import Literal, Protocol

from fastapi import Request, Response
from pydantic import BaseModel, Field

from relay.config import Settings


class IssueDraft(BaseModel):
    """Normalized issue payload produced by a chat adapter."""

    title: str = Field(min_length=1)
    description: str | None = None
    source: Literal["discord", "slack"]
    author: str
    channel: str | None = None

    def linear_description(self) -> str:
        """Markdown description including provenance for Linear."""
        parts: list[str] = []
        if self.description:
            parts.append(self.description.strip())
            parts.append("")
        parts.append("---")
        parts.append(f"**Source:** {self.source}")
        parts.append(f"**Author:** {self.author}")
        if self.channel:
            parts.append(f"**Channel:** {self.channel}")
        return "\n".join(parts)


class CreatedIssue(BaseModel):
    """Result of a successful Linear issueCreate."""

    identifier: str
    url: str


class CreateIssueFn(Protocol):
    """Callable that creates a Linear issue from a draft."""

    async def __call__(self, draft: IssueDraft) -> CreatedIssue: ...


class ChatAdapter(Protocol):
    """Pluggable chat webhook adapter."""

    name: str

    def enabled(self, settings: Settings) -> bool: ...

    async def handle(
        self,
        request: Request,
        settings: Settings,
        *,
        create_issue: CreateIssueFn,
    ) -> Response: ...
