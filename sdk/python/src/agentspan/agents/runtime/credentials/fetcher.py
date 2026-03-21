# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""WorkerCredentialFetcher — resolves credentials for a Conductor task.

Resolution order:
  1. If execution token present: POST /api/credentials/resolve
  2. On 401: raise CredentialAuthError (no fallback)
  3. On 429: raise CredentialRateLimitError (no fallback)
  4. On 5xx + strict_mode: raise CredentialServiceError
  5. On 5xx + non-strict: env var fallback with warning
  6. Names missing from 200 response + non-strict: env var fallback
  7. Names missing from 200 response + strict: raise CredentialNotFoundError
  8. If token absent (local dev): env var fallback directly
"""

from __future__ import annotations

import logging
import os
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
        server_url: Base URL of the agentspan server API (e.g. ``"http://localhost:8080/api"``).
        strict_mode: When ``True``, disables env var fallback entirely.
        api_key: Optional Bearer token or API key for the Authorization header.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8080/api",
        strict_mode: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._strict_mode = strict_mode
        self._api_key = api_key

    # ── Public API ──────────────────────────────────────────────────────

    def fetch(
        self,
        execution_token: Optional[str],
        names: List[str],
    ) -> Dict[str, str]:
        """Resolve credential values for *names* in this execution context.

        Args:
            execution_token: The ``__agentspan_ctx__`` token from Conductor task
                variables. ``None`` or empty string means local dev (no server).
            names: Logical credential names to resolve (e.g. ``["GITHUB_TOKEN"]``).

        Returns:
            Dict mapping credential name → plaintext value for names that were
            resolved. Names absent from the result were not found anywhere.

        Raises:
            CredentialAuthError: Token expired/revoked (401). Never retried.
            CredentialRateLimitError: Rate limit hit (429). Never retried.
            CredentialServiceError: Server 5xx in strict_mode.
            CredentialNotFoundError: Name(s) missing everywhere in strict_mode.
        """
        if not names:
            return {}

        if not execution_token:
            # Local dev / no server — go straight to env
            return self._env_fallback(names, require_all=self._strict_mode)

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
            # Network-level error — treat like 5xx
            logger.warning("Credential service unreachable: %s", exc)
            if self._strict_mode:
                raise CredentialServiceError(0, str(exc)) from exc
            logger.warning(
                "Falling back to env vars for %s (credential service unreachable)", names
            )
            return self._env_fallback(names, require_all=False)

        status = response.status_code

        if status == 401:
            raise CredentialAuthError(response.text)

        if status == 429:
            raise CredentialRateLimitError()

        if status >= 500:
            if self._strict_mode:
                raise CredentialServiceError(status, response.text)
            logger.warning(
                "Credential service returned %d; falling back to env vars for %s",
                status,
                names,
            )
            return self._env_fallback(names, require_all=False)

        # 200 OK
        resolved: Dict[str, str] = response.json()
        missing = [n for n in names if n not in resolved]
        if missing:
            if self._strict_mode:
                raise CredentialNotFoundError(missing)
            env_resolved = self._env_fallback(missing, require_all=False)
            resolved.update(env_resolved)
            still_missing = [n for n in missing if n not in env_resolved]
            if still_missing:
                logger.debug("Credentials not found anywhere: %s", still_missing)

        return resolved

    def _env_fallback(
        self,
        names: List[str],
        require_all: bool = False,
    ) -> Dict[str, str]:
        """Read *names* from ``os.environ``.

        Args:
            names: Names to look up.
            require_all: When ``True``, raise ``CredentialNotFoundError`` if
                any name is absent from the environment.
        """
        result = {n: os.environ[n] for n in names if n in os.environ}
        if require_all:
            missing = [n for n in names if n not in result]
            if missing:
                raise CredentialNotFoundError(missing)
        return result
