"""Domain exceptions mapped to HTTP responses by the app."""

from __future__ import annotations


class RelayError(Exception):
    """Base error for Relay."""


class SignatureError(RelayError):
    """Webhook signature verification failed."""


class AdapterDisabledError(RelayError):
    """Requested chat adapter is not configured."""


class LinearError(RelayError):
    """Linear API call failed."""


class ValidationError(RelayError):
    """User-facing input validation failure (e.g. empty title)."""
