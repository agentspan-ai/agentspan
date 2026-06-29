# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credential exception hierarchy."""

from __future__ import annotations

from typing import List

from conductor.ai.agents.exceptions import AgentspanError


class CredentialNotFoundError(AgentspanError):
    """One or more required credentials could not be resolved.

    Raised when a declared credential is not found in the credential store.
    There is no env var fallback for declared credentials — store them with
    ``agentspan credentials set --name <NAME>``.
    """

    def __init__(self, missing_names: List[str], detail: str = "") -> None:
        self.missing_names = list(missing_names)
        names_str = ", ".join(missing_names)
        msg = f"Required credentials not found: {names_str}"
        if detail:
            msg += f". {detail}"
        super().__init__(msg)


class CredentialAuthError(AgentspanError):
    """Execution token is invalid, expired, or revoked.

    Raised on HTTP 401 from ``/api/workers/credentials``.
    Do NOT retry and do NOT fall through to env var fallback.
    """

    def __init__(self, detail: str = "") -> None:
        msg = "Credential authentication failed (token expired or revoked)"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class CredentialRateLimitError(AgentspanError):
    """Rate limit exceeded on ``/api/workers/credentials`` (HTTP 429).

    Do NOT fall through to env var fallback.
    """

    def __init__(self) -> None:
        super().__init__(
            "Credential resolution rate limit exceeded (429). "
            "Reduce resolve call frequency or increase the server rate limit."
        )


class CredentialServiceError(AgentspanError):
    """Credential service returned a 5xx error or is unreachable.

    Always fatal — no env var fallback.

    Attributes:
        status_code: The HTTP status code (e.g. 503), or 0 for network errors.
    """

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        msg = f"Credential service error (HTTP {status_code})"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)
