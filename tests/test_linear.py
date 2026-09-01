"""Linear client unit tests."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from relay.adapters.base import IssueDraft
from relay.config import Settings
from relay.exceptions import LinearError
from relay.linear.client import LinearClient


def _settings() -> Settings:
    return Settings.from_worker_bindings(
        linear_api_key=SecretStr("lin_test"),
        linear_team_id="team-uuid",
    )


@pytest.mark.asyncio
async def test_create_issue_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "identifier": "ENG-42",
                            "url": "https://linear.app/x/issue/ENG-42",
                        },
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = LinearClient(http=http, settings=_settings())
        issue = await client.create_issue(
            IssueDraft(
                title="Fix login",
                description=None,
                source="slack",
                author="harsh",
                channel="eng",
            )
        )
    assert issue.identifier == "ENG-42"
    assert "ENG-42" in issue.url


@pytest.mark.asyncio
async def test_list_projects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "projects": {
                        "nodes": [
                            {"id": "p1", "name": "Mobile"},
                            {"id": "p2", "name": "Web"},
                        ]
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = LinearClient(http=http, settings=_settings())
        projects = await client.list_projects("mo")
    assert len(projects) == 2
    assert projects[0].name == "Mobile"


@pytest.mark.asyncio
async def test_create_issue_with_project_and_priority() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body["variables"])
        return httpx.Response(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "identifier": "ENG-9",
                            "url": "https://linear.app/x/issue/ENG-9",
                        },
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = LinearClient(http=http, settings=_settings())
        await client.create_issue(
            IssueDraft(
                title="Fix login",
                source="discord",
                author="harsh",
                channel=None,
                project_id="proj-1",
                priority=2,
            )
        )
    assert seen["projectId"] == "proj-1"
    assert seen["priority"] == 2


@pytest.mark.asyncio
async def test_create_issue_graphql_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "nope"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = LinearClient(http=http, settings=_settings())
        with pytest.raises(LinearError):
            await client.create_issue(
                IssueDraft(
                    title="x",
                    source="discord",
                    author="a",
                    channel=None,
                )
            )
