#!/usr/bin/env python3
"""Register (or update) the Discord /issue slash command.

Requires DISCORD_APPLICATION_ID and DISCORD_BOT_TOKEN in `.env`.

Run again after changing options (project autocomplete, priority, etc.).
"""

from __future__ import annotations

import sys

import httpx

from relay.config import Settings

COMMAND = {
    "name": "issue",
    "description": "Create a Linear issue",
    "type": 1,
    "options": [
        {
            "name": "title",
            "description": "Issue title",
            "type": 3,
            "required": True,
        },
        {
            "name": "description",
            "description": "Optional issue description",
            "type": 3,
            "required": False,
        },
        {
            "name": "project",
            "description": "Linear project (type to search)",
            "type": 3,
            "required": False,
            "autocomplete": True,
        },
        {
            "name": "priority",
            "description": "Issue priority",
            "type": 4,
            "required": False,
            "choices": [
                {"name": "Urgent", "value": 1},
                {"name": "High", "value": 2},
                {"name": "Normal", "value": 3},
                {"name": "Low", "value": 4},
            ],
        },
    ],
}


def main() -> int:
    settings = Settings()
    app_id = settings.discord_application_id
    token = settings.discord_bot_token
    if not app_id or token is None:
        print(
            "Set DISCORD_APPLICATION_ID and DISCORD_BOT_TOKEN in .env",
            file=sys.stderr,
        )
        return 1

    url = f"https://discord.com/api/v10/applications/{app_id}/commands"
    headers = {
        "Authorization": f"Bot {token.get_secret_value()}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=COMMAND)

    if response.status_code >= 400:
        print(
            f"Discord API error {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        return 1

    data = response.json()
    print(f"Registered /{data.get('name')} (id={data.get('id')})")
    print("Options: title, description, project (autocomplete), priority")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
