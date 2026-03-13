# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Configuration — load settings from environment variables and ``.env`` files.

Uses ``pydantic-settings`` :class:`BaseSettings` so values are automatically
read from env vars and an optional ``.env`` file in the working directory.

Usage::

    config = AgentConfig()                     # auto-loads from env / .env
    config = AgentConfig(server_url="http://custom:8080/api")  # explicit override
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Configuration for the agents runtime.

    Values are loaded from environment variables (and an optional ``.env``
    file) with sensible defaults. Simply instantiate with ``AgentConfig()``.

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    server_url: str = Field(
        default="http://localhost:8080/api",
        validation_alias="AGENTSPAN_SERVER_URL",
    )
    auth_key: Optional[str] = Field(
        default=None,
        validation_alias="AGENTSPAN_AUTH_KEY",
    )
    auth_secret: Optional[str] = Field(
        default=None,
        validation_alias="AGENTSPAN_AUTH_SECRET",
    )
    default_timeout_seconds: int = Field(
        default=0,
        validation_alias="AGENTSPAN_AGENT_TIMEOUT",
    )
    llm_retry_count: int = Field(
        default=3,
        validation_alias="AGENTSPAN_LLM_RETRY_COUNT",
    )
    worker_poll_interval_ms: int = Field(
        default=100,
        validation_alias="AGENTSPAN_WORKER_POLL_INTERVAL",
    )
    worker_thread_count: int = Field(
        default=1,
        validation_alias="AGENTSPAN_WORKER_THREADS",
    )
    auto_start_workers: bool = Field(
        default=True,
        validation_alias="AGENTSPAN_AUTO_START_WORKERS",
    )
    auto_start_server: bool = Field(
        default=True,
        validation_alias="AGENTSPAN_AUTO_START_SERVER",
    )
    daemon_workers: bool = Field(
        default=True,
        validation_alias="AGENTSPAN_DAEMON_WORKERS",
    )
    auto_register_integrations: bool = Field(
        default=False,
        validation_alias="AGENTSPAN_INTEGRATIONS_AUTO_REGISTER",
    )
    streaming_enabled: bool = Field(
        default=True,
        validation_alias="AGENTSPAN_STREAMING_ENABLED",
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
