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

# JS verifier — keeps TypedArrays and Promises entirely on the JS side.
_DISCORD_VERIFY_JS = """
return (async () => {
  const hexToU8 = (hex) => {
    const clean = String(hex).trim().replace(/^0x/i, "");
    if (clean.length % 2 !== 0) {
      throw new Error("invalid hex length");
    }
    const out = new Uint8Array(clean.length / 2);
    for (let i = 0; i < out.length; i++) {
      out[i] = parseInt(clean.substr(i * 2, 2), 16);
    }
    return out;
  };

  const publicKey = hexToU8(publicKeyHex);
  const signature = hexToU8(signatureHex);
  const body = Uint8Array.from(bodyBytes);
  const tsBytes = new TextEncoder().encode(String(timestamp));
  const message = new Uint8Array(tsBytes.length + body.length);
  message.set(tsBytes, 0);
  message.set(body, tsBytes.length);

  const key = await crypto.subtle.importKey(
    "raw",
    publicKey,
    { name: "Ed25519" },
    false,
    ["verify"]
  );
  return await crypto.subtle.verify("Ed25519", key, signature, message);
})()
"""


def _js_truthy(value: Any) -> bool:
    """Convert a JS/Pyodide value to a real Python bool."""
    if value is True or value is False:
        return value
    if value == True:  # noqa: E712 — JsProxy equality
        return True
    if value == False:  # noqa: E712
        return False
    to_py = getattr(value, "to_py", None)
    if callable(to_py):
        return bool(to_py())
    return bool(value)


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
        from js import Function  # type: ignore[import-not-found]
    except ImportError:
        raise SignatureError(
            "Discord Ed25519 verification requires the Workers Web Crypto API"
        ) from None

    try:
        # body as a plain list of ints — JS builds Uint8Array (avoids FFI buffer bugs)
        verify = Function.new(
            "publicKeyHex",
            "signatureHex",
            "timestamp",
            "bodyBytes",
            _DISCORD_VERIFY_JS,
        )
        result = await verify(
            public_key_hex.strip(),
            signature_hex.strip(),
            timestamp,
            list(body),
        )
    except SignatureError:
        raise
    except Exception as exc:
        logger.warning("Discord signature verification error: %s", type(exc).__name__)
        raise SignatureError("Invalid Discord signature") from exc

    if not _js_truthy(result):
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
