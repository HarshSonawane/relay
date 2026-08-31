"""API and adapter integration tests."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from relay.adapters.base import CreatedIssue
from relay.config import Settings
from relay.deps import get_settings
from relay.main import create_app


def _settings(**overrides: Any) -> Settings:
    data: dict[str, Any] = {
        "linear_api_key": SecretStr("lin_test"),
        "linear_team_id": "team-uuid",
        "discord_public_key": "a" * 64,
        "slack_signing_secret": SecretStr("slack_secret"),
    }
    data.update(overrides)
    return Settings.model_validate(data)


def _slack_sig(secret: str, timestamp: str, body: bytes) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    settings = _settings()

    def _override() -> Settings:
        return settings

    app.dependency_overrides[get_settings] = _override

    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["adapters"]["discord"] is True
    assert body["adapters"]["slack"] is True
    assert body["linear"] is True


def test_hooks_unknown_provider(client: TestClient) -> None:
    response = client.post("/hooks/teams")
    assert response.status_code == 404


def test_hooks_discord_disabled() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(
        discord_public_key=None,
    )
    with TestClient(app) as test_client:
        response = test_client.post("/hooks/discord", content=b"{}")
    assert response.status_code == 404


def test_slack_issue_create(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    settings = _settings()
    app.dependency_overrides[get_settings] = lambda: settings

    created = CreatedIssue(
        identifier="ENG-1",
        url="https://linear.app/team/issue/ENG-1",
    )
    mock_create = AsyncMock(return_value=created)

    async def _fake_create(self: Any, draft: Any) -> CreatedIssue:
        return await mock_create(draft)

    monkeypatch.setattr(
        "relay.linear.client.LinearClient.create_issue",
        _fake_create,
    )

    body = (
        b"token=x&team_id=T1&channel_id=C1&channel_name=eng"
        b"&user_id=U1&user_name=harsh&command=%2Fissue"
        b"&text=Fix+login+%7C+users+cannot+SSO"
    )
    timestamp = str(int(time.time()))
    signature = _slack_sig("slack_secret", timestamp, body)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/hooks/slack",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Signature": signature,
                "X-Slack-Request-Timestamp": timestamp,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response_type"] == "in_channel"
    assert "ENG-1" in data["text"]
    mock_create.assert_awaited_once()
    draft = mock_create.await_args.args[0]
    assert draft.title == "Fix login"
    assert draft.description == "users cannot SSO"
    assert draft.source == "slack"


def test_slack_empty_title() -> None:
    app = create_app()
    settings = _settings()
    app.dependency_overrides[get_settings] = lambda: settings

    body = b"token=x&user_name=harsh&command=%2Fissue&text="
    timestamp = str(int(time.time()))
    signature = _slack_sig("slack_secret", timestamp, body)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/hooks/slack",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Signature": signature,
                "X-Slack-Request-Timestamp": timestamp,
            },
        )

    assert response.status_code == 200
    assert response.json()["response_type"] == "ephemeral"
    assert "Title is required" in response.json()["text"]
