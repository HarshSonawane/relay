"""Slack command parsing for project / priority."""

from __future__ import annotations

from relay.adapters.slack import SlackAdapter


def test_slack_parse_project_and_priority() -> None:
    adapter = SlackAdapter()
    draft = adapter._parse_command(
        {
            "text": [
                "Fix login | users cannot SSO | project:Mobile | priority:high"
            ],
            "user_name": ["harsh"],
            "channel_name": ["eng"],
        }
    )
    assert draft.title == "Fix login"
    assert draft.description == "users cannot SSO"
    assert draft.project_name == "Mobile"
    assert draft.priority == 2
