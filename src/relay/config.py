"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Fast, high free-tier RPD on Groq; override with GROQ_MODEL if needed.
_DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


class Settings(BaseSettings):
    """Typed settings loaded from Worker bindings or a local `.env` file.

    Env var names match field names uppercased (LINEAR_API_KEY, etc.).
    Secrets use SecretStr so they do not appear in logs or ``repr()``.

    Linear keys are optional at load time so Discord PING verification can
    succeed even if Linear is not configured yet; issue creation still requires
    them (see ``require_linear``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    linear_api_key: SecretStr | None = None
    linear_team_id: str | None = None

    discord_public_key: str | None = None
    discord_application_id: str | None = None
    discord_bot_token: SecretStr | None = None
    slack_signing_secret: SecretStr | None = None

    groq_api_key: SecretStr | None = None
    groq_model: str = _DEFAULT_GROQ_MODEL

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_public_key)

    @property
    def slack_enabled(self) -> bool:
        return self.slack_signing_secret is not None

    @property
    def groq_enabled(self) -> bool:
        return self.groq_api_key is not None

    def require_linear(self) -> None:
        """Raise if Linear credentials are missing (call before API use)."""
        if self.linear_api_key is None or not self.linear_team_id:
            from relay.exceptions import LinearError

            raise LinearError(
                "LINEAR_API_KEY and LINEAR_TEAM_ID must be set as Worker secrets"
            )
