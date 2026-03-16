# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Configuration — load settings from environment variables.

Uses ``dataclasses`` with a ``from_env()`` classmethod for env var loading.
Constructor kwargs allow direct overrides (useful for tests).

Usage::

    config = AgentConfig.from_env()                          # load from env
    config = AgentConfig(server_url="http://custom:8080/api")  # explicit
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env(var: str, default=None):
    """Read an environment variable, returning *default* if unset."""
    return os.environ.get(var, default)


def _env_bool(var: str, default: bool = False) -> bool:
    """Read a boolean environment variable (true/1/yes → True)."""
    val = os.environ.get(var)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


def _env_int(var: str, default: int = 0) -> int:
    """Read an integer environment variable."""
    val = os.environ.get(var)
    if val is None:
        return default
    return int(val)


@dataclass
class AgentConfig:
    """Configuration for the agents runtime.

    Values are loaded from environment variables via ``from_env()``.
    Direct construction with kwargs is supported for tests and explicit config.

    Attributes:
        server_url: Agentspan server API URL.
        auth_key: Auth key (optional for OSS).
        auth_secret: Auth secret (optional for OSS).
        default_timeout_seconds: Default workflow timeout.
        worker_poll_interval_ms: Worker polling interval in milliseconds.
        worker_thread_count: Number of threads per worker.
        auto_start_workers: Whether to auto-start worker processes.
        daemon_workers: Whether worker processes are daemon (killed on exit).
        auto_start_server: Whether to auto-start the local server process
            when the server URL points to localhost and the server is not
            already running.  Set to ``False`` for remote/production servers.
        auto_register_integrations: When ``True``, automatically create LLM
            integrations and register models on the Conductor server before
            executing agents.  Reads API keys from provider-specific env vars
            (e.g. ``OPENAI_API_KEY``).
    """

    server_url: str = "http://localhost:8080/api"
    auth_key: Optional[str] = None
    auth_secret: Optional[str] = None
    default_timeout_seconds: int = 0
    llm_retry_count: int = 3
    worker_poll_interval_ms: int = 100
    worker_thread_count: int = 1
    auto_start_workers: bool = True
    auto_start_server: bool = True
    daemon_workers: bool = True
    auto_register_integrations: bool = False
    streaming_enabled: bool = True

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Create an ``AgentConfig`` by reading ``AGENTSPAN_*`` env vars."""
        return cls(
            server_url=_env("AGENTSPAN_SERVER_URL", "http://localhost:8080/api"),
            auth_key=_env("AGENTSPAN_AUTH_KEY"),
            auth_secret=_env("AGENTSPAN_AUTH_SECRET"),
            default_timeout_seconds=_env_int("AGENTSPAN_AGENT_TIMEOUT", 0),
            llm_retry_count=_env_int("AGENTSPAN_LLM_RETRY_COUNT", 3),
            worker_poll_interval_ms=_env_int("AGENTSPAN_WORKER_POLL_INTERVAL", 100),
            worker_thread_count=_env_int("AGENTSPAN_WORKER_THREADS", 1),
            auto_start_workers=_env_bool("AGENTSPAN_AUTO_START_WORKERS", True),
            auto_start_server=_env_bool("AGENTSPAN_AUTO_START_SERVER", True),
            daemon_workers=_env_bool("AGENTSPAN_DAEMON_WORKERS", True),
            auto_register_integrations=_env_bool("AGENTSPAN_INTEGRATIONS_AUTO_REGISTER", False),
            streaming_enabled=_env_bool("AGENTSPAN_STREAMING_ENABLED", True),
        )

    @property
    def api_key(self) -> Optional[str]:
        """Alias for :attr:`auth_key` (industry-standard naming)."""
        return self.auth_key

    @property
    def api_secret(self) -> Optional[str]:
        """Alias for :attr:`auth_secret` (industry-standard naming)."""
        return self.auth_secret

    def to_conductor_configuration(self) -> "Configuration":
        """Convert to a ``conductor-python`` :class:`Configuration` object."""
        from conductor.client.configuration.configuration import Configuration

        config = Configuration(server_api_url=self.server_url)
        if self.auth_key:
            from conductor.client.configuration.settings.authentication_settings import AuthenticationSettings
            config.authentication_settings = AuthenticationSettings(
                key_id=self.auth_key,
                key_secret=self.auth_secret or "",
            )
        return config
