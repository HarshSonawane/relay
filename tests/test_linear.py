"""Linear client unit tests."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from relay.adapters.base import IssueDraft
from relay.config import Settings
from relay.exceptions import LinearError
from relay.linear.client import LinearClient


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "linear_api_key": SecretStr("lin_test"),
            "linear_team_id": "team-uuid",
        }
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
