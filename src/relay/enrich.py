"""Groq-powered issue draft enrichment for short/unclear messages."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from relay.adapters.base import IssueDraft
from relay.config import Settings

logger = logging.getLogger("relay.enrich")

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Titles at or below this length (chars) are treated as thin.
_SHORT_TITLE_CHARS = 24
# Titles with this many words or fewer need help unless description is rich.
_SHORT_TITLE_WORDS = 4
# Description this short (or missing) counts as thin.
_THIN_DESCRIPTION_CHARS = 40

_VAGUE_TITLES = frozenset(
    {
        "bug",
        "bugs",
        "issue",
        "issues",
        "error",
        "errors",
        "fix",
        "help",
        "broken",
        "problem",
        "problems",
        "asap",
        "urgent",
        "please",
        "test",
        "todo",
        "wip",
        "something",
        "stuff",
        "fail",
        "failed",
        "failure",
        "not working",
        "doesnt work",
        "doesn't work",
        "please fix",
        "fix it",
        "fix this",
        "check this",
        "look at this",
    }
)

_SYSTEM_PROMPT = """\
You improve vague bug/feature reports into clear Linear issue drafts.

Rules:
- Output ONLY valid JSON with keys "title" and "description" (strings).
- title: concise, specific, actionable (max ~80 chars). No trailing period.
- description: 2-5 short markdown bullets covering what, where, and what is unknown.
- Do NOT invent product names, URLs, or stack traces that were not implied.
- Preserve the reporter's intent. If the input is already clear, only lightly polish.
- Keep the original meaning; never refuse — always produce a useful draft.
"""


class EnrichmentResult(BaseModel):
    title: str = Field(min_length=1)
    description: str


def needs_enrichment(draft: IssueDraft) -> bool:
    """Return True when the draft looks too short or unclear for Linear."""
    title = " ".join(draft.title.split()).strip()
    title_lower = title.lower().rstrip(".!?")
    desc = (draft.description or "").strip()
    words = [w for w in re.split(r"\s+", title) if w]

    if title_lower in _VAGUE_TITLES:
        return True
    if len(title) <= _SHORT_TITLE_CHARS:
        return True
    if len(words) <= _SHORT_TITLE_WORDS and len(desc) < _THIN_DESCRIPTION_CHARS:
        return True
    return not desc and len(words) <= _SHORT_TITLE_WORDS + 1


class IssueEnricher:
    """Rewrite unclear drafts via Groq's OpenAI-compatible chat API."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def enrich(self, draft: IssueDraft) -> IssueDraft:
        """Return an improved draft, or the original if Groq is off / fails."""
        if not self._settings.groq_enabled:
            return draft
        if not needs_enrichment(draft):
            return draft

        try:
            result = await self._call_groq(draft)
        except Exception:
            logger.exception("Groq enrichment failed; using original draft")
            return draft

        original_title = draft.title.strip()
        original_desc = (draft.description or "").strip()
        provenance = [
            result.description.strip(),
            "",
            "---",
            f"**Original title:** {original_title}",
        ]
        if original_desc:
            provenance.append(f"**Original description:** {original_desc}")
        provenance.append("_Improved by Groq_")

        return draft.model_copy(
            update={
                "title": result.title.strip() or draft.title,
                "description": "\n".join(provenance),
            }
        )

    async def _call_groq(self, draft: IssueDraft) -> EnrichmentResult:
        assert self._settings.groq_api_key is not None
        user_payload = {
            "title": draft.title,
            "description": draft.description,
            "source": draft.source,
        }
        body: dict[str, Any] = {
            "model": self._settings.groq_model,
            "temperature": 0.2,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
        }
        response = await self._http.post(
            _GROQ_URL,
            headers={
                "Authorization": (
                    f"Bearer {self._settings.groq_api_key.get_secret_value()}"
                ),
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code >= 400:
            logger.error("Groq HTTP %s", response.status_code)
            msg = f"Groq returned HTTP {response.status_code}"
            raise RuntimeError(msg)

        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            raise RuntimeError("Groq returned empty content")

        parsed = json.loads(content)
        return EnrichmentResult.model_validate(parsed)
