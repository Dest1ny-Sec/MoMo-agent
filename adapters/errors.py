"""Platform-level error classification.

All platform-specific exceptions (TSec / Mock / future CTFd / HackTheBox)
should be normalized into a small set of canonical categories so the
orchestrator can make scheduling decisions without knowing the platform.
"""
from __future__ import annotations


class PlatformError(Exception):
    """Base for any platform-side failure.

    Adapters should raise subclasses of this so the orchestrator can
    catch by category.
    """

    def __init__(self, code: str, message: str, http_status: int | None = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.http_status = http_status


class AuthError(PlatformError):
    """Token invalid / expired. Non-recoverable; stop the run."""


class RateLimitError(PlatformError):
    """We are being throttled. Back off and retry later."""


class NetworkError(PlatformError):
    """Connection failed / timeout. Retry with backoff."""


class DuplicateFlagError(PlatformError):
    """This flag was already submitted for this challenge."""


class InvalidStateError(PlatformError):
    """Challenge is in an unexpected state (closed / expired / etc)."""

    # On TSec this maps to "invalid_state" → task ended.


class NotFoundError(PlatformError):
    """Challenge / endpoint does not exist."""


class TransientError(PlatformError):
    """Server side hiccup; safe to retry."""
