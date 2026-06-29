# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""SDK-level exceptions for the agentspan agents package.

Provides a consistent exception hierarchy so users don't need to catch
library-specific HTTP errors from ``requests`` or ``httpx``.
"""

from __future__ import annotations


class AgentspanError(Exception):
    """Base exception for all agentspan SDK errors."""


class AgentAPIError(AgentspanError):
    """An HTTP error from the agent runtime API."""

    def __init__(self, status_code: int, message: str, url: str = ""):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"HTTP {status_code}: {message}" + (f" ({url})" if url else ""))


class AgentNotFoundError(AgentAPIError):
    """Raised when the workflow/agent ID is not found (404)."""


def _raise_api_error(exc: Exception, url: str = "") -> None:
    """Convert an HTTP library exception to an SDK exception and raise it.

    Handles both ``requests.HTTPError`` and ``httpx.HTTPStatusError``.
    """
    status_code = 0
    message = str(exc)

    # requests.HTTPError
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        status_code = exc.response.status_code
        try:
            body = exc.response.text
        except Exception:
            body = message
        message = body or message

    # httpx.HTTPStatusError
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        status_code = exc.response.status_code
        try:
            message = exc.response.text or message
        except Exception:
            pass

    if status_code == 404:
        raise AgentNotFoundError(status_code, message, url) from exc
    raise AgentAPIError(status_code, message, url) from exc
