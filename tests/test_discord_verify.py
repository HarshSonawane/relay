"""Discord Ed25519 verification tests (pure Python)."""

from __future__ import annotations

import os

import pytest

from relay._ed25519 import publickey_unsafe, signature_unsafe
from relay.crypto import verify_discord_ed25519
from relay.exceptions import SignatureError


def test_discord_verify_ok() -> None:
    sk = os.urandom(32)
    pk = publickey_unsafe(sk)
    body = b'{"type":1}'
    timestamp = "1710000000"
    message = timestamp.encode() + body
    sig = signature_unsafe(message, sk, pk)

    verify_discord_ed25519(
        body=body,
        signature_hex=sig.hex(),
        timestamp=timestamp,
        public_key_hex=pk.hex(),
    )


def test_discord_verify_bad_sig() -> None:
    sk = os.urandom(32)
    pk = publickey_unsafe(sk)
    with pytest.raises(SignatureError):
        verify_discord_ed25519(
            body=b'{"type":1}',
            signature_hex="00" * 64,
            timestamp="1710000000",
            public_key_hex=pk.hex(),
        )


def test_discord_verify_wrong_key_length() -> None:
    with pytest.raises(SignatureError, match="32 bytes"):
        verify_discord_ed25519(
            body=b"{}",
            signature_hex="00" * 64,
            timestamp="1",
            public_key_hex="abcd",
        )
