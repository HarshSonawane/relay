"""Linear GraphQL client."""

from __future__ import annotations

import logging

import httpx

from relay.adapters.base import CreatedIssue, IssueDraft
from relay.config import Settings
from relay.exceptions import LinearError

logger = logging.getLogger("relay.linear")

_LINEAR_URL = "https://api.linear.app/graphql"

_CREATE_ISSUE = """
mutation CreateIssue($teamId: String!, $title: String!, $description: String) {
  issueCreate(input: { teamId: $teamId, title: $title, description: $description }) {
    success
    issue {
      identifier
      url
    }
  }
}
""".strip()


class LinearClient:
    """Thin async client for Linear issueCreate."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def create_issue(self, draft: IssueDraft) -> CreatedIssue:
        headers = {
            "Authorization": self._settings.linear_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        payload = {
            "query": _CREATE_ISSUE,
            "variables": {
                "teamId": self._settings.linear_team_id,
                "title": draft.title,
                "description": draft.linear_description(),
            },
        }

        try:
            response = await self._http.post(
                _LINEAR_URL,
                headers=headers,
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.error("Linear request failed: %s", type(exc).__name__)
            raise LinearError("Failed to reach Linear") from exc

        if response.status_code >= 400:
            logger.error("Linear HTTP %s", response.status_code)
            raise LinearError(f"Linear returned HTTP {response.status_code}")

        data = response.json()
        if "errors" in data:
            logger.error("Linear GraphQL errors present")
            raise LinearError("Linear GraphQL error")

        result = data.get("data", {}).get("issueCreate")
        if not result or not result.get("success") or not result.get("issue"):
            raise LinearError("Linear issueCreate did not succeed")

        issue = result["issue"]
        return CreatedIssue(identifier=issue["identifier"], url=issue["url"])
