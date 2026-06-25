# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""WorkerCredentialFetcher — resolves credentials for a Conductor task.

Credentials are ALWAYS resolved from the server via POST /api/workers/credentials.
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
        auth_key: Optional[str] = None,
        auth_secret: Optional[str] = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._strict_mode = strict_mode  # kept for backwards compat but not used
        self._api_key = api_key
        # Orkes-host deployments gate every /api/* call behind a session token
        # minted from a key/secret pair at POST /api/token (sent as the
        # ``X-Authorization`` header). The raw key id is NOT a valid bearer, so
        # when a key/secret pair is present we exchange it and cache the result.
        self._auth_key = auth_key
        self._auth_secret = auth_secret
        self._session_token_cache: Optional[str] = None

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

    def _session_token(self, *, refresh: bool = False) -> Optional[str]:
        """Return a cached orkes session token, minting one on first use.

        Orkes-host deployments require a session JWT (minted from key id +
        secret at ``POST /api/token``) on every ``/api/*`` call. Returns ``None``
        when no key/secret pair is configured (standalone agentspan, where the
        execution token in the request body is the only credential required).
        """
        if not (self._auth_key and self._auth_secret):
            return None
        if self._session_token_cache and not refresh:
            return self._session_token_cache
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                resp = client.post(
                    f"{self._server_url}/token",
                    json={"keyId": self._auth_key, "keySecret": self._auth_secret},
                    headers={"Content-Type": "application/json"},
                )
            resp.raise_for_status()
            self._session_token_cache = resp.json().get("token")
        except Exception as exc:  # noqa: BLE001 — surfaced as an auth failure downstream
            logger.error("Failed to mint orkes session token: %s", exc)
            self._session_token_cache = None
        return self._session_token_cache

    def _auth_headers(self, *, refresh: bool = False) -> Dict[str, str]:
        """Build the gateway auth headers for an /api/* call.

        Prefers an orkes session token (``X-Authorization``); falls back to a
        static ``Authorization: Bearer`` api key for standalone deployments.
        """
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        session = self._session_token(refresh=refresh)
        if session:
            headers["X-Authorization"] = session
        elif self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _fetch_from_server(
        self,
        execution_token: str,
        names: List[str],
    ) -> Dict[str, str]:
        # Server endpoint was renamed to /workers/secrets (Conductor parity);
        # the SDK keeps the credentials terminology on the user-facing side.
        url = f"{self._server_url}/workers/secrets"
        payload = {"token": execution_token, "names": names}

        def _post(refresh: bool):
            try:
                with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                    return client.post(url, json=payload, headers=self._auth_headers(refresh=refresh))
            except httpx.RequestError as exc:
                logger.error("Credential service unreachable: %s", exc)
                raise CredentialServiceError(0, str(exc)) from exc

        response = _post(refresh=False)
        # A 401 may mean the cached session token expired — refresh once and retry.
        if response.status_code == 401 and self._auth_key and self._auth_secret:
            response = _post(refresh=True)

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
