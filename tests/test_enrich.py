"""Tests for unclear-message detection and Groq enrichment."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from relay.adapters.base import IssueDraft
from relay.config import Settings
from relay.enrich import IssueEnricher, needs_enrichment


def _draft(
    title: str,
    description: str | None = None,
    *,
    source: str = "slack",
) -> IssueDraft:
    return IssueDraft(
        title=title,
        description=description,
        source=source,  # type: ignore[arg-type]
        author="harsh",
        channel="eng",
    )


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "linear_api_key": SecretStr("lin_test"),
        "linear_team_id": "team-uuid",
        "groq_api_key": SecretStr("gsk_test"),
        "groq_model": "llama-3.1-8b-instant",
    }
    data.update(overrides)
    return Settings.model_validate(data)


def test_needs_enrichment_vague_title() -> None:
    assert needs_enrichment(_draft("bug")) is True
    assert needs_enrichment(_draft("fix it")) is True
    assert needs_enrichment(_draft("not working")) is True


def test_needs_enrichment_short_title() -> None:
    assert needs_enrichment(_draft("login broken")) is True


def test_needs_enrichment_clear_skip() -> None:
    draft = _draft(
        "SSO login fails on mobile Safari with 401 after OTP",
        "Repro: open app → OTP → lands on error screen. Started after deploy 1.4.2.",
    )
    assert needs_enrichment(draft) is False


@pytest.mark.asyncio
async def test_enrich_rewrites_vague_draft() -> None:
    payload = {
        "title": "Mobile SSO login returns 401 after OTP",
        "description": "- Happens on mobile\n- After OTP step\n- Need logs",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["model"] == "llama-3.1-8b-instant"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(payload)}},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        enricher = IssueEnricher(http=http, settings=_settings())
        result = await enricher.enrich(_draft("bug"))

    assert result.title == payload["title"]
    assert "Original title:** bug" in result.description
    assert "Improved by Groq" in result.description


@pytest.mark.asyncio
async def test_enrich_skipped_when_clear() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500, json={"error": "should not call"})

    draft = _draft(
        "SSO login fails on mobile Safari with 401 after OTP",
        "Repro steps and deploy version included here for clarity.",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        enricher = IssueEnricher(http=http, settings=_settings())
        result = await enricher.enrich(draft)

    assert called is False
    assert result.title == draft.title


@pytest.mark.asyncio
async def test_enrich_falls_back_on_groq_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    draft = _draft("bug")
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        enricher = IssueEnricher(http=http, settings=_settings())
        result = await enricher.enrich(draft)

    assert result.title == "bug"
    assert result.description is None


@pytest.mark.asyncio
async def test_enrich_noop_without_api_key() -> None:
    draft = _draft("bug")
    async with httpx.AsyncClient() as http:
        enricher = IssueEnricher(
            http=http,
            settings=_settings(groq_api_key=None),
        )
        result = await enricher.enrich(draft)
    assert result.title == "bug"
