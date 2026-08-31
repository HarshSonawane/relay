"""Cloudflare Workers entrypoint.

Wrangler ``main`` must live next to the ``relay`` package directory so
``import relay`` resolves at deploy time. Application code stays in ``relay/``.
"""

from __future__ import annotations

from relay.main import Default, app, create_app

__all__ = ["Default", "app", "create_app"]
