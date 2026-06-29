# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Auth token helpers shared by the sync/async agent API clients and framework adapters.

Secured Conductor hosts (e.g. orkes) authenticate API calls with a JWT in the
``X-Authorization`` header, minted from an application access key via
``POST {server}/token``. These helpers centralize that mint (with an expiry-aware
process-wide cache) so every HTTP path — agent API, SSE streaming, framework event
pushes — sends the same correct header. Anonymous servers ignore the header.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger("conductor.ai.agents.token_utils")


def decode_jwt_exp(token: str) -> float:
    """Best-effort decode of a JWT's ``exp`` claim (unix seconds).

    Returns 0.0 for opaque tokens, malformed JWTs, or tokens without ``exp`` —
    callers treat 0 as "expiry unknown, use until rejected".
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return 0.0
        seg = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(seg))
        return float(payload.get("exp", 0) or 0)
    except Exception:
        return 0.0


# Process-wide mint cache: (server_url, auth_key) -> (token, exp). Framework event
# pushes run on thread pools, so guard with a lock.
_TOKEN_CACHE: Dict[Tuple[str, str], Tuple[str, float]] = {}
_TOKEN_LOCK = threading.Lock()


def resolve_agent_api_token(
    server_url: str,
    api_key: Optional[str] = None,
    auth_key: Optional[str] = None,
    auth_secret: Optional[str] = None,
) -> Optional[str]:
    """Resolve the JWT for agent API calls.

    An explicit ``api_key`` is already a token and returned as-is. Otherwise a JWT is
    minted from ``auth_key``/``auth_secret`` via ``POST {server_url}/token`` and cached
    until ~expiry. Returns None when no credentials are configured or the mint fails
    (anonymous / security-disabled servers).
    """
    if api_key:
        return api_key
    if not auth_key or not auth_secret:
        return None

    import time

    cache_key = (server_url.rstrip("/"), auth_key)
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached:
            token, exp = cached
            if exp == 0.0 or time.time() < exp - 30:
                return token

    import requests

    url = server_url.rstrip("/") + "/token"
    try:
        resp = requests.post(url, json={"keyId": auth_key, "keySecret": auth_secret}, timeout=30)
        resp.raise_for_status()
        token = resp.json().get("token")
    except Exception as e:  # pragma: no cover - network/credential failures
        logger.warning("Failed to mint agent API token: %s", e)
        return None
    if not token:
        return None
    with _TOKEN_LOCK:
        _TOKEN_CACHE[cache_key] = (token, decode_jwt_exp(token))
    return token


def agent_api_auth_headers(
    server_url: str,
    api_key: Optional[str] = None,
    auth_key: Optional[str] = None,
    auth_secret: Optional[str] = None,
) -> Dict[str, str]:
    """``X-Authorization`` header dict for agent API calls ({} when anonymous)."""
    token = resolve_agent_api_token(server_url, api_key, auth_key, auth_secret)
    return {"X-Authorization": token} if token else {}
