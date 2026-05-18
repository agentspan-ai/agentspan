# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""WorkerCredentialFetcher — resolves credentials for a Conductor task.

Credentials are ALWAYS resolved from the server via POST /api/credentials/resolve.
There is no env var fallback. If the execution token is missing or credentials
are not stored on the server, the tool fails with a non-retryable error.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import httpx

from agentspan.agents.runtime.credentials.types import (
    CredentialAuthError,
    CredentialNotFoundError,
    CredentialRateLimitError,
    CredentialServiceError,
)

logger = logging.getLogger("agentspan.agents.credentials.fetcher")


class WorkerCredentialFetcher:
    """Fetches credentials for a worker task execution.

    Args:
        server_url: Base URL of the agentspan server API (e.g. ``"http://localhost:6767/api"``).
        api_key: Optional Bearer token or API key for the Authorization header.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:6767/api",
        strict_mode: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._strict_mode = strict_mode  # kept for backwards compat but not used
        self._api_key = api_key

    # ── Public API ──────────────────────────────────────────────────────

    def fetch(
        self,
        execution_token: Optional[str],
        names: List[str],
    ) -> Dict[str, str]:
        """Resolve credential values for *names* from the server.

        Credentials are always fetched from the server. There is no env var
        fallback. If the execution token is missing, this raises
        CredentialNotFoundError so the task fails with a non-retryable error.

        Args:
            execution_token: The ``__agentspan_ctx__`` token from Conductor task
                variables.
            names: Logical credential names to resolve (e.g. ``["GITHUB_TOKEN"]``).

        Returns:
            Dict mapping credential name → plaintext value.

        Raises:
            CredentialAuthError: Token expired/revoked (401).
            CredentialRateLimitError: Rate limit hit (429).
            CredentialServiceError: Server unreachable or 5xx.
            CredentialNotFoundError: Credential(s) not found on server or no token.
        """
        if not names:
            return {}

        if not execution_token:
            raise CredentialNotFoundError(
                names,
                "No execution token available. "
                "Store credentials on the server with: agentspan credentials set --name <NAME>",
            )

        return self._fetch_from_server(execution_token, names)

    # ── Private helpers ─────────────────────────────────────────────────

    def _fetch_from_server(
        self,
        execution_token: str,
        names: List[str],
    ) -> Dict[str, str]:
        url = f"{self._server_url}/credentials/resolve"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                response = client.post(
                    url,
                    json={"token": execution_token, "names": names},
                    headers=headers,
                )
        except httpx.RequestError as exc:
            logger.error("Credential service unreachable: %s", exc)
            raise CredentialServiceError(0, str(exc)) from exc

        status = response.status_code

        if status == 401:
            raise CredentialAuthError(response.text)

        if status == 429:
            raise CredentialRateLimitError()

        if status >= 500:
            raise CredentialServiceError(status, response.text)

        # 200 OK — check for missing credentials
        resolved: Dict[str, str] = response.json()
        missing = [n for n in names if n not in resolved]
        if missing:
            logger.error(
                "Credentials not found on server: %s. "
                "Store them with: agentspan credentials set --name <NAME>",
                missing,
            )
            raise CredentialNotFoundError(missing)

        return resolved

