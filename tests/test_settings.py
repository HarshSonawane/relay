"""Settings loading tests."""

from __future__ import annotations

from pydantic import SecretStr

from relay.config import Settings


def test_settings_from_dict() -> None:
    settings = Settings.model_validate(
        {
            "linear_api_key": "lin_key",
            "linear_team_id": "team-1",
            "discord_public_key": "abc",
            "groq_api_key": "gsk_test",
        }
    )
    assert settings.linear_team_id == "team-1"
    assert isinstance(settings.linear_api_key, SecretStr)
    assert settings.discord_enabled is True
    assert settings.slack_enabled is False
    assert settings.groq_enabled is True
    assert settings.groq_model == "llama-3.1-8b-instant"


def test_secret_str_hidden_in_repr() -> None:
    settings = Settings.model_validate(
        {
            "linear_api_key": "super-secret",
            "linear_team_id": "team-1",
        }
    )
    assert "super-secret" not in repr(settings)
