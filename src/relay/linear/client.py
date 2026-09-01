"""Linear GraphQL client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from relay.adapters.base import CreatedIssue, IssueDraft, LinearProject
from relay.config import Settings
from relay.exceptions import LinearError

logger = logging.getLogger("relay.linear")

_LINEAR_URL = "https://api.linear.app/graphql"

_CREATE_ISSUE = """
mutation CreateIssue(
  $teamId: String!
  $title: String!
  $description: String
  $projectId: String
  $priority: Int
) {
  issueCreate(
    input: {
      teamId: $teamId
      title: $title
      description: $description
      projectId: $projectId
      priority: $priority
    }
  ) {
    success
    issue {
      identifier
      url
    }
  }
}
""".strip()

_LIST_PROJECTS = """
query ListProjects($filter: ProjectFilter) {
  projects(filter: $filter, first: 25) {
    nodes {
      id
      name
    }
  }
}
""".strip()


class LinearClient:
    """Thin async client for Linear issueCreate / project listing."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        self._settings.require_linear()
        assert self._settings.linear_api_key is not None
        return {
            "Authorization": self._settings.linear_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }

    async def _graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._http.post(
                _LINEAR_URL,
                headers=self._headers(),
                json={"query": query, "variables": variables or {}},
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
        return data.get("data") or {}

    async def list_projects(self, query: str = "") -> list[LinearProject]:
        """Return up to 25 projects, optionally filtered by name contains."""
        variables: dict[str, Any] = {}
        q = query.strip()
        if q:
            variables["filter"] = {"name": {"containsIgnoreCase": q}}

        data = await self._graphql(_LIST_PROJECTS, variables)
        nodes = (data.get("projects") or {}).get("nodes") or []
        return [
            LinearProject(id=n["id"], name=n["name"])
            for n in nodes
            if isinstance(n, dict) and n.get("id") and n.get("name")
        ]

    async def resolve_project_id(self, name: str) -> LinearProject | None:
        """Find a project by exact (case-insensitive) name, else best contains."""
        projects = await self.list_projects(name)
        if not projects:
            return None
        lowered = name.strip().lower()
        for project in projects:
            if project.name.lower() == lowered:
                return project
        return projects[0]

    async def create_issue(self, draft: IssueDraft) -> CreatedIssue:
        self._settings.require_linear()
        assert self._settings.linear_team_id is not None

        variables: dict[str, Any] = {
            "teamId": self._settings.linear_team_id,
            "title": draft.title,
            "description": draft.linear_description(),
            "projectId": draft.project_id,
            "priority": draft.priority,
        }

        data = await self._graphql(_CREATE_ISSUE, variables)
        result = data.get("issueCreate")
        if not result or not result.get("success") or not result.get("issue"):
            raise LinearError("Linear issueCreate did not succeed")

        issue = result["issue"]
        return CreatedIssue(identifier=issue["identifier"], url=issue["url"])
