"""Signature verification helpers.

Discord: pure-Python Ed25519 verify (Pyodide-safe; no Web Crypto FFI).
Slack: stdlib HMAC-SHA256 (v0 signing scheme).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from relay._ed25519 import SignatureMismatch, checkvalid
from relay.exceptions import SignatureError

logger = logging.getLogger("relay.crypto")

_SLACK_MAX_AGE_SECONDS = 60 * 5


def verify_discord_ed25519(
    *,
    body: bytes,
    signature_hex: str,
    timestamp: str,
    public_key_hex: str,
) -> None:
    """Verify a Discord interaction signature.

    Raises SignatureError on failure.

    Uses a pure-Python Ed25519 verifier (public-message safe) so we do not
    depend on Pyodide Web Crypto FFI, which has been unreliable here.
    """
    if not signature_hex or not timestamp or not public_key_hex:
        raise SignatureError("Missing Discord signature headers or public key")

    try:
        public_key = bytes.fromhex(public_key_hex.strip().removeprefix("0x"))
        signature = bytes.fromhex(signature_hex.strip().removeprefix("0x"))
    except ValueError as exc:
        raise SignatureError("Invalid Discord signature encoding") from exc

    if len(public_key) != 32:
        raise SignatureError(
            f"Discord public key must be 32 bytes (got {len(public_key)})"
        )
    if len(signature) != 64:
        raise SignatureError(
            f"Discord signature must be 64 bytes (got {len(signature)})"
        )

    if isinstance(body, str):
        body = body.encode("utf-8")
    message = timestamp.encode("utf-8") + body

    try:
        checkvalid(signature, message, public_key)
    except SignatureMismatch as exc:
        raise SignatureError("Invalid Discord signature") from exc
    except ValueError as exc:
        logger.warning("Discord signature decode error: %s", exc)
        raise SignatureError("Invalid Discord signature") from exc


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
