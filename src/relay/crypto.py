"""Signature verification helpers.

Discord uses Workers Web Crypto Ed25519 via the JS FFI.
Slack uses stdlib HMAC-SHA256 (v0 signing scheme).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

from relay.exceptions import SignatureError

logger = logging.getLogger("relay.crypto")

_SLACK_MAX_AGE_SECONDS = 60 * 5


def _as_u8(data: bytes) -> Any:
    """Copy Python bytes into a JS Uint8Array for Web Crypto."""
    from js import Uint8Array  # type: ignore[import-not-found]

    arr = Uint8Array.new(len(data))
    arr.assign(data)
    return arr


async def verify_discord_ed25519(
    *,
    body: bytes,
    signature_hex: str,
    timestamp: str,
    public_key_hex: str,
) -> None:
    """Verify a Discord interaction signature.

    Raises SignatureError on failure.
    """
    if not signature_hex or not timestamp or not public_key_hex:
        raise SignatureError("Missing Discord signature headers or public key")

    try:
        from js import crypto
    except ImportError:
        raise SignatureError(
            "Discord Ed25519 verification requires the Workers Web Crypto API"
        ) from None

    try:
        public_key_bytes = bytes.fromhex(public_key_hex.strip())
        signature_bytes = bytes.fromhex(signature_hex.strip())
        message = timestamp.encode("utf-8") + body

        key = await crypto.subtle.importKey(
            "raw",
            _as_u8(public_key_bytes),
            {"name": "Ed25519"},
            False,
            ["verify"],
        )
        valid = await crypto.subtle.verify(
            "Ed25519",
            key,
            _as_u8(signature_bytes),
            _as_u8(message),
        )
    except SignatureError:
        raise
    except Exception as exc:
        logger.warning("Discord signature verification error: %s", type(exc).__name__)
        raise SignatureError("Invalid Discord signature") from exc

    if not valid:
        raise SignatureError("Invalid Discord signature")


def verify_slack_signature(
    *,
    body: bytes,
    signature: str,
    timestamp: str,
    signing_secret: str,
    now: float | None = None,
) -> None:
    """Verify a Slack request signature (v0).

    Raises SignatureError on failure or replay (stale timestamp).
    """
    try:
        ts = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise SignatureError("Invalid Slack timestamp") from exc

    current = time.time() if now is None else now
    if abs(current - ts) > _SLACK_MAX_AGE_SECONDS:
        raise SignatureError("Slack timestamp too old")

    basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()
    expected = f"v0={digest}"

    if not hmac.compare_digest(expected, signature):
        raise SignatureError("Invalid Slack signature")
