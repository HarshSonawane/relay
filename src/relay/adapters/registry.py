"""Adapter registry."""

from __future__ import annotations

from relay.adapters.base import ChatAdapter
from relay.adapters.discord import DiscordAdapter
from relay.adapters.slack import SlackAdapter

_ADAPTERS: dict[str, ChatAdapter] = {
    DiscordAdapter.name: DiscordAdapter(),
    SlackAdapter.name: SlackAdapter(),
}


def get_adapter(name: str) -> ChatAdapter | None:
    return _ADAPTERS.get(name)


def known_providers() -> list[str]:
    return sorted(_ADAPTERS)
