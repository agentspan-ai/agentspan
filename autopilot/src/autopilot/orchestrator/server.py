"""Server API client — wraps the Agentspan execution query API.

Provides clean functions to query agent executions from the running
Agentspan server at ``/api/agent/executions``.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from autopilot.config import AutopilotConfig

logger = logging.getLogger(__name__)

# Default timeout for server requests (seconds).
_DEFAULT_TIMEOUT = 10.0


def _base_url(config: Optional[AutopilotConfig] = None) -> str:
    """Return the server base URL from config or defaults."""
    if config is None:
        config = AutopilotConfig.from_env()
    return config.server_url.rstrip("/")


def query_executions(
    status: Optional[str] = None,
    agent_name: Optional[str] = None,
    config: Optional[AutopilotConfig] = None,
) -> list[dict]:
    """Query the Agentspan server for executions.

    Args:
        status: Filter by execution status (e.g. ``"RUNNING"``, ``"COMPLETED"``).
        agent_name: Filter by agent name.
        config: Optional config override. Defaults to ``AutopilotConfig.from_env()``.

    Returns:
        List of execution result dicts from the server.

    Raises:
        httpx.HTTPStatusError: If the server returns a non-2xx response.
        httpx.ConnectError: If the server is unreachable.
    """
    url = f"{_base_url(config)}/api/agent/executions"
    params: dict[str, str] = {}
    if status is not None:
        params["status"] = status
    if agent_name is not None:
        params["agentName"] = agent_name

    resp = httpx.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


def get_execution(
    execution_id: str,
    config: Optional[AutopilotConfig] = None,
) -> dict:
    """Get details for a specific execution.

    Args:
        execution_id: The execution ID to look up.
        config: Optional config override.

    Returns:
        Execution detail dict from the server.

    Raises:
        httpx.HTTPStatusError: If the server returns a non-2xx response.
        httpx.ConnectError: If the server is unreachable.
    """
    url = f"{_base_url(config)}/api/agent/executions/{execution_id}"
    resp = httpx.get(url, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_running_agents(
    config: Optional[AutopilotConfig] = None,
) -> list[dict]:
    """Get all currently running agent executions.

    Convenience wrapper around :func:`query_executions` with ``status="RUNNING"``.

    Args:
        config: Optional config override.

    Returns:
        List of running execution result dicts.
    """
    return query_executions(status="RUNNING", config=config)
