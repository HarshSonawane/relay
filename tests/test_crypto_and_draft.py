"""Tests for Slack signature verification and IssueDraft."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from relay.adapters.base import IssueDraft
from relay.crypto import verify_slack_signature
from relay.exceptions import SignatureError


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_verify_slack_signature_ok() -> None:
    secret = "test_signing_secret"
    body = b"token=x&text=Fix+login"
    timestamp = str(int(time.time()))
    signature = _sign(secret, timestamp, body)
    verify_slack_signature(
        body=body,
        signature=signature,
        timestamp=timestamp,
        signing_secret=secret,
    )


def test_verify_slack_signature_bad() -> None:
    with pytest.raises(SignatureError):
        verify_slack_signature(
            body=b"text=hi",
            signature="v0=deadbeef",
            timestamp=str(int(time.time())),
            signing_secret="secret",
        )


def test_verify_slack_signature_stale() -> None:
    secret = "secret"
    body = b"text=hi"
    timestamp = str(int(time.time()) - 600)
    signature = _sign(secret, timestamp, body)
    with pytest.raises(SignatureError, match="too old"):
        verify_slack_signature(
            body=body,
            signature=signature,
            timestamp=timestamp,
            signing_secret=secret,
        )


def test_issue_draft_linear_description() -> None:
    draft = IssueDraft(
        title="Fix login",
        description="users cannot SSO",
        source="slack",
        author="harsh",
        channel="eng",
    )
    md = draft.linear_description()
    assert "users cannot SSO" in md
    assert "**Source:** slack" in md
    assert "**Author:** harsh" in md
    assert "**Channel:** eng" in md
