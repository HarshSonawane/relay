"""Shared adapter models and protocol."""

from __future__ import annotations

from typing import Literal, Protocol

from fastapi import Request, Response
from pydantic import BaseModel, Field

from relay.config import Settings

Priority = Literal[0, 1, 2, 3, 4]

_PRIORITY_LABELS: dict[int, str] = {
    0: "None",
    1: "Urgent",
    2: "High",
    3: "Normal",
    4: "Low",
}


class IssueDraft(BaseModel):
    """Normalized issue payload produced by a chat adapter."""

    title: str = Field(min_length=1)
    description: str | None = None
    source: Literal["discord", "slack"]
    author: str
    channel: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    priority: Priority | None = None

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
        if self.project_name:
            parts.append(f"**Project:** {self.project_name}")
        if self.priority is not None:
            label = _PRIORITY_LABELS.get(self.priority, str(self.priority))
            parts.append(f"**Priority:** {label}")
        return "\n".join(parts)


class CreatedIssue(BaseModel):
    """Result of a successful Linear issueCreate."""

    identifier: str
    url: str


class LinearProject(BaseModel):
    """A Linear project available for selection."""

    id: str
    name: str


class CreateIssueFn(Protocol):
    """Callable that creates a Linear issue from a draft."""

    async def __call__(self, draft: IssueDraft) -> CreatedIssue: ...


class ListProjectsFn(Protocol):
    """Callable that lists Linear projects for autocomplete."""

    async def __call__(self, query: str) -> list[LinearProject]: ...


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
        list_projects: ListProjectsFn,
    ) -> Response: ...
