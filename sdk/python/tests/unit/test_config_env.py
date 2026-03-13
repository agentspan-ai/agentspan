# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for AgentConfig environment variable loading.

Verifies that AGENTSPAN_* env vars are loaded correctly.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

from agentspan.agents.runtime.config import AgentConfig, _env


class TestEnvHelper:
    """Tests for the _env() helper function."""

    def test_reads_agentspan_var(self):
        with mock.patch.dict(os.environ, {"AGENTSPAN_FOO": "bar"}, clear=False):
            assert _env("AGENTSPAN_FOO", "AGENTSPAN_FOO") == "bar"

    def test_falls_back_to_conductor_var(self):
        env = {"AGENTSPAN_FOO": "legacy"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AGENTSPAN_FOO", None)
            assert _env("AGENTSPAN_FOO", "AGENTSPAN_FOO") == "legacy"

    def test_agentspan_takes_precedence(self):
        env = {"AGENTSPAN_FOO": "new", "AGENTSPAN_FOO": "old"}
        with mock.patch.dict(os.environ, env, clear=False):
            assert _env("AGENTSPAN_FOO", "AGENTSPAN_FOO") == "new"

    def test_returns_default_when_neither_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env("AGENTSPAN_FOO", "AGENTSPAN_FOO", "default") == "default"

    def test_returns_none_when_no_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env("AGENTSPAN_FOO", "AGENTSPAN_FOO") is None


class TestAgentConfigFromEnv:
    """Tests for AgentConfig.from_env()."""

    def test_reads_agentspan_server_url(self):
        env = {"AGENTSPAN_SERVER_URL": "http://myhost:9090/api"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://myhost:9090/api"

    def test_falls_back_to_conductor_server_url(self):
        env = {"AGENTSPAN_SERVER_URL": "http://legacy:7001/api"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://legacy:7001/api"

    def test_agentspan_url_takes_precedence(self):
        env = {
            "AGENTSPAN_SERVER_URL": "http://new:8080/api",
            "AGENTSPAN_SERVER_URL": "http://old:7001/api",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://new:8080/api"

    def test_defaults_to_localhost_when_nothing_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://localhost:8080/api"

    def test_reads_agentspan_auth_key(self):
        env = {"AGENTSPAN_AUTH_KEY": "mykey", "AGENTSPAN_AUTH_SECRET": "mysecret"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.auth_key == "mykey"
            assert config.auth_secret == "mysecret"

    def test_falls_back_to_conductor_auth(self):
        env = {"AGENTSPAN_AUTH_KEY": "oldkey", "AGENTSPAN_AUTH_SECRET": "oldsecret"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.auth_key == "oldkey"
            assert config.auth_secret == "oldsecret"

    def test_auto_start_server_defaults_true(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = AgentConfig.from_env()
            assert config.auto_start_server is True

    def test_auto_start_server_env_false(self):
        env = {"AGENTSPAN_AUTO_START_SERVER": "false"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.auto_start_server is False

    def test_boolean_env_vars(self):
        env = {
            "AGENTSPAN_DAEMON_WORKERS": "false",
            "AGENTSPAN_INTEGRATIONS_AUTO_REGISTER": "true",
            "AGENTSPAN_STREAMING_ENABLED": "no",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.daemon_workers is False
            assert config.auto_register_integrations is True
            assert config.streaming_enabled is False

    def test_numeric_env_vars(self):
        env = {
            "AGENTSPAN_AGENT_TIMEOUT": "120",
            "AGENTSPAN_LLM_RETRY_COUNT": "5",
            "AGENTSPAN_WORKER_THREADS": "4",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.default_timeout_seconds == 120
            assert config.llm_retry_count == 5
            assert config.worker_thread_count == 4


class TestServerAutoStart:
    """Tests for server auto-start utilities."""

    def test_is_localhost_true(self):
        from agentspan.agents.runtime.server import _is_localhost

        assert _is_localhost("http://localhost:8080/api") is True
        assert _is_localhost("http://127.0.0.1:8080/api") is True
        assert _is_localhost("http://[::1]:8080/api") is True

    def test_is_localhost_false(self):
        from agentspan.agents.runtime.server import _is_localhost

        assert _is_localhost("http://example.com:8080/api") is False
        assert _is_localhost("http://10.0.0.1:8080/api") is False

    def test_ensure_server_running_skips_remote(self):
        from agentspan.agents.runtime.server import ensure_server_running

        # Should return immediately for non-localhost URLs (no HTTP call)
        ensure_server_running("http://remote-host:8080/api")

    def test_ensure_server_running_skips_empty(self):
        from agentspan.agents.runtime.server import ensure_server_running

        ensure_server_running("")

    @mock.patch("agentspan.agents.runtime.server._is_server_ready", return_value=True)
    def test_ensure_server_running_noop_when_ready(self, mock_ready):
        from agentspan.agents.runtime.server import ensure_server_running

        ensure_server_running("http://localhost:8080/api")
        mock_ready.assert_called_once()

    @mock.patch("agentspan.agents.runtime.server._is_server_ready", return_value=True)
    @mock.patch("agentspan.agents.runtime.server.ensure_server_running")
    def test_auto_start_server_false_skips_ensure(self, mock_ensure, mock_ready):
        """When auto_start_server=False, ensure_server_running is NOT called."""
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.runtime import AgentRuntime

        config = AgentConfig(
            server_url="http://localhost:8080/api",
            auto_start_server=False,
        )
        with mock.patch("conductor.client.orkes_clients.OrkesClients"):
            with mock.patch("agentspan.agents.runtime.worker_manager.WorkerManager"):
                rt = AgentRuntime(config=config)
        mock_ensure.assert_not_called()

    @mock.patch("agentspan.agents.runtime.server._is_server_ready", return_value=False)
    def test_auto_start_server_false_exits_on_unreachable(self, mock_ready):
        """When auto_start_server=False and server is down, exit with message."""
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.runtime import AgentRuntime

        config = AgentConfig(
            server_url="http://localhost:8080/api",
            auto_start_server=False,
        )
        with pytest.raises(SystemExit, match="1"):
            AgentRuntime(config=config)

    @mock.patch("agentspan.agents.runtime.server.time")
    @mock.patch("agentspan.agents.runtime.server.subprocess")
    @mock.patch("agentspan.agents.runtime.server._find_or_install_cli", return_value="/usr/local/bin/agentspan")
    @mock.patch("agentspan.agents.runtime.server._is_server_ready", side_effect=[False, False, True])
    def test_ensure_server_running_starts_server(
        self, mock_ready, mock_find_cli, mock_subprocess, mock_time
    ):
        from agentspan.agents.runtime.server import ensure_server_running

        mock_time.monotonic.side_effect = [0, 1, 2, 3]
        mock_time.sleep = mock.MagicMock()

        ensure_server_running("http://localhost:8080/api")

        mock_subprocess.run.assert_called_once_with(
            ["/usr/local/bin/agentspan", "server", "start"],
            stdout=mock.ANY,
            stderr=mock.ANY,
        )
