# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Configuration — load settings from environment variables.

Uses ``dataclasses`` with a ``from_env()`` classmethod for env var loading.
Constructor kwargs allow direct overrides (useful for tests).

Usage::

    config = AgentConfig.from_env()                          # load from env
    config = AgentConfig(server_url="http://custom:6767/api")  # explicit
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional


def _env(var: str, default=None):
    """Read an environment variable, returning *default* if unset."""
    return os.environ.get(var, default)


logger = logging.getLogger("agentspan.agents.config")


def _env_bool(var: str, default: bool = False) -> bool:
    """Read a boolean environment variable (true/1/yes → True)."""
    val = os.environ.get(var)
    if val is None or val.strip() == "":
        return default
    return val.lower() in ("true", "1", "yes")


def _env_int(var: str, default: int = 0) -> int:
    """Read an integer environment variable."""
    val = os.environ.get(var)
    if val is None or val.strip() == "":
        return default
    return int(val)


@dataclass
class AgentConfig:
    """Configuration for the agents runtime.

    Attributes:
        server_url: Agentspan server API URL.
        api_key: Bearer token or static API key for the Authorization header.
            Preferred over auth_key/auth_secret for new deployments.
        auth_key: Auth key (kept for backward compatibility).
        auth_secret: Auth secret (kept for backward compatibility).
        worker_poll_interval_ms: Worker polling interval in milliseconds.
        worker_thread_count: Number of threads per worker.
        auto_start_workers: Whether to auto-start worker processes.
        daemon_workers: Whether worker processes are daemon (killed on exit).
        auto_start_server: Whether to auto-start the local server process.
        auto_register_integrations: Auto-create LLM integrations on startup.
        credential_strict_mode: When ``True``, disables env var fallback for
            credential resolution. Required credentials must come from the
            credential service.
        log_level: Logging level for the agentspan logger.
    """

    server_url: str = "http://localhost:6767/api"
    api_key: Optional[str] = None
    auth_key: Optional[str] = None
    auth_secret: Optional[str] = None
    llm_retry_count: int = 3
    worker_poll_interval_ms: int = 100
    worker_thread_count: int = 1
    auto_start_workers: bool = True
    auto_start_server: bool = True
    daemon_workers: bool = True
    auto_register_integrations: bool = False
    streaming_enabled: bool = True
    credential_strict_mode: bool = False
    log_level: str = "INFO"

    def __post_init__(self):
        """Normalise server_url: auto-append /api if missing."""
        if self.server_url:
            stripped = self.server_url.rstrip("/")
            if not stripped.endswith("/api"):
                logger.info(
                    "server_url %r does not end with '/api' — appending automatically.",
                    self.server_url,
                )
                self.server_url = stripped + "/api"
            else:
                self.server_url = stripped

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Create an ``AgentConfig`` by reading ``AGENTSPAN_*`` env vars."""
        log_level = _env("AGENTSPAN_LOG_LEVEL", "INFO")
        if isinstance(log_level, str) and log_level.strip() == "":
            log_level = "INFO"
        return cls(
            server_url=_env("AGENTSPAN_SERVER_URL", "http://localhost:6767/api"),
            api_key=_env("AGENTSPAN_API_KEY"),
            auth_key=_env("AGENTSPAN_AUTH_KEY"),
            auth_secret=_env("AGENTSPAN_AUTH_SECRET"),
            llm_retry_count=_env_int("AGENTSPAN_LLM_RETRY_COUNT", 3),
            worker_poll_interval_ms=_env_int("AGENTSPAN_WORKER_POLL_INTERVAL", 100),
            worker_thread_count=_env_int("AGENTSPAN_WORKER_THREADS", 1),
            auto_start_workers=_env_bool("AGENTSPAN_AUTO_START_WORKERS", True),
            auto_start_server=_env_bool("AGENTSPAN_AUTO_START_SERVER", True),
            daemon_workers=_env_bool("AGENTSPAN_DAEMON_WORKERS", True),
            auto_register_integrations=_env_bool("AGENTSPAN_INTEGRATIONS_AUTO_REGISTER", False),
            streaming_enabled=_env_bool("AGENTSPAN_STREAMING_ENABLED", True),
            credential_strict_mode=_env_bool("AGENTSPAN_CREDENTIAL_STRICT_MODE", False),
            log_level=log_level,
        )

    @property
    def api_secret(self) -> Optional[str]:
        """Alias for :attr:`auth_secret` (industry-standard naming)."""
        return self.auth_secret

    def to_conductor_configuration(self) -> "Configuration":  # noqa: F821
        """Convert to a ``conductor-python`` :class:`Configuration` object."""
        from conductor.client.configuration.configuration import Configuration

        config = Configuration(server_api_url=self.server_url)
        # Propagate our log level to the Conductor logger process.
        # Configuration.log_level has no public setter (only debug=True/False),
        # so we write the private attribute directly.
        import logging as _logging
        config._Configuration__log_level = getattr(_logging, self.log_level.upper(), _logging.INFO)
        # Prefer api_key; fall back to auth_key for backward compat
        effective_key = self.api_key or self.auth_key
        if effective_key:
            from conductor.client.configuration.settings.authentication_settings import (
                AuthenticationSettings,
            )

            config.authentication_settings = AuthenticationSettings(
                key_id=effective_key,
                key_secret=self.auth_secret or "",
            )
        return config
