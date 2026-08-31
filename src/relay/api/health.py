"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter

from relay.deps import SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(settings: SettingsDep) -> dict[str, object]:
    """Liveness plus which adapters/secrets the Worker can see at runtime."""
    return {
        "status": "ok",
        "adapters": {
            "discord": settings.discord_enabled,
            "slack": settings.slack_enabled,
        },
        "linear": bool(settings.linear_api_key and settings.linear_team_id),
        "groq": settings.groq_enabled,
    }
