"""Cloudflare Workers entrypoint.

Wrangler ``main`` must live next to the ``relay`` package directory so
``import relay`` resolves at deploy time. Application code stays in ``relay/``.

Uses an explicit WorkerEntrypoint so ``self.env`` (secrets) is always passed
into the ASGI scope as ``request.scope["env"]``.
"""

from __future__ import annotations

from workers import WorkerEntrypoint, asgi

from relay.main import app, create_app

__all__ = ["Default", "app", "create_app"]


class Default(WorkerEntrypoint):
    async def fetch(self, request):  # type: ignore[no-untyped-def]
        return await asgi.fetch(app, request, self.env, self.ctx)
