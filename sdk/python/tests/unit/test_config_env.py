# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for AgentConfig environment variable loading.

Verifies that AGENTSPAN_* env vars are loaded correctly via from_env().
"""

from __future__ import annotations

import os
from unittest import mock

from agentspan.agents.runtime.config import AgentConfig, _env, _env_bool, _env_int


class TestEnvHelper:
    """Tests for the _env() helper function."""

    def test_reads_var(self):
        with mock.patch.dict(os.environ, {"AGENTSPAN_FOO": "bar"}, clear=False):
            assert _env("AGENTSPAN_FOO") == "bar"

    def test_returns_default_when_not_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env("AGENTSPAN_FOO", "default") == "default"

    def test_returns_none_when_no_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env("AGENTSPAN_FOO") is None


class TestEnvBool:
    """Tests for _env_bool() helper."""

    def test_true_values(self):
        for val in ("true", "True", "TRUE", "1", "yes"):
            with mock.patch.dict(os.environ, {"FLAG": val}, clear=True):
                assert _env_bool("FLAG") is True, f"Failed for {val!r}"

    def test_false_values(self):
        for val in ("false", "False", "0", "no"):
            with mock.patch.dict(os.environ, {"FLAG": val}, clear=True):
                assert _env_bool("FLAG") is False, f"Failed for {val!r}"

    def test_default_true(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env_bool("FLAG", True) is True

    def test_default_false(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env_bool("FLAG", False) is False

    def test_empty_string_uses_default(self):
        with mock.patch.dict(os.environ, {"FLAG": ""}, clear=True):
            assert _env_bool("FLAG", True) is True


class TestEnvInt:
    """Tests for _env_int() helper."""

    def test_reads_int(self):
        with mock.patch.dict(os.environ, {"NUM": "42"}, clear=True):
            assert _env_int("NUM") == 42

    def test_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _env_int("NUM", 7) == 7

    def test_empty_string_uses_default(self):
        with mock.patch.dict(os.environ, {"NUM": ""}, clear=True):
            assert _env_int("NUM", 7) == 7


class TestAgentConfigFromEnv:
    """Tests for AgentConfig.from_env()."""

    def test_reads_agentspan_server_url(self):
        env = {"AGENTSPAN_SERVER_URL": "http://myhost:9090/api"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://myhost:9090/api"

    def test_defaults_to_localhost_when_nothing_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://localhost:6767/api"

    def test_reads_agentspan_auth_key(self):
        env = {"AGENTSPAN_AUTH_KEY": "mykey", "AGENTSPAN_AUTH_SECRET": "mysecret"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.auth_key == "mykey"
            assert config.auth_secret == "mysecret"

    def test_reads_auth_key_via_env(self):
        env = {"AGENTSPAN_AUTH_KEY": "key2"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.auth_key == "key2"
            # api_key is a separate field populated from AGENTSPAN_API_KEY
            assert config.api_key is None

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
            "AGENTSPAN_LLM_RETRY_COUNT": "5",
            "AGENTSPAN_WORKER_THREADS": "4",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = AgentConfig.from_env()
            assert config.llm_retry_count == 5
            assert config.worker_thread_count == 4

    def test_direct_construction(self):
        config = AgentConfig(server_url="http://test:9090/api")
        assert config.server_url == "http://test:9090/api"


class TestServerUrlNormalisation:
    """Tests for BUG-P2-10: auto-append /api when missing."""

    def test_appends_api_when_missing(self):
        config = AgentConfig(server_url="http://localhost:6767")
        assert config.server_url == "http://localhost:6767/api"

    def test_appends_api_with_trailing_slash(self):
        config = AgentConfig(server_url="http://localhost:6767/")
        assert config.server_url == "http://localhost:6767/api"

    def test_leaves_correct_url_unchanged(self):
        config = AgentConfig(server_url="http://localhost:6767/api")
        assert config.server_url == "http://localhost:6767/api"

    def test_leaves_correct_url_with_trailing_slash(self):
        config = AgentConfig(server_url="http://localhost:6767/api/")
        assert config.server_url == "http://localhost:6767/api"

    def test_remote_url_without_api(self):
        config = AgentConfig(server_url="https://play.orkes.io")
        assert config.server_url == "https://play.orkes.io/api"

    def test_from_env_auto_appends(self):
        with mock.patch.dict(
            os.environ, {"AGENTSPAN_SERVER_URL": "http://myhost:9090"}, clear=True
        ):
            config = AgentConfig.from_env()
            assert config.server_url == "http://myhost:9090/api"

    def test_default_url_has_api(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = AgentConfig.from_env()
            assert config.server_url == "http://localhost:6767/api"


class TestLogLevelConfig:
    """Tests for BUG-P3-04: log_level configuration field."""

    def test_default_log_level(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = AgentConfig.from_env()
            assert config.log_level == "INFO"

    def test_log_level_from_env(self):
        with mock.patch.dict(os.environ, {"AGENTSPAN_LOG_LEVEL": "WARNING"}, clear=True):
            config = AgentConfig.from_env()
            assert config.log_level == "WARNING"

    def test_log_level_debug(self):
        with mock.patch.dict(os.environ, {"AGENTSPAN_LOG_LEVEL": "DEBUG"}, clear=True):
            config = AgentConfig.from_env()
            assert config.log_level == "DEBUG"

    def test_log_level_empty_string_uses_default(self):
        with mock.patch.dict(os.environ, {"AGENTSPAN_LOG_LEVEL": ""}, clear=True):
            config = AgentConfig.from_env()
            assert config.log_level == "INFO"

    @mock.patch("agentspan.agents.runtime.server._is_server_ready", return_value=True)
    def test_log_level_applied_to_logger(self, mock_ready):
        """AgentRuntime.__init__ applies log_level to the agentspan logger."""
        import logging

        config = AgentConfig(
            server_url="http://localhost:6767/api",
            log_level="WARNING",
        )
        with mock.patch("conductor.client.orkes_clients.OrkesClients"):
            with mock.patch("agentspan.agents.runtime.worker_manager.WorkerManager"):
                from agentspan.agents.runtime.runtime import AgentRuntime

                rt = AgentRuntime(config=config)

        assert logging.getLogger("agentspan").level == logging.WARNING
        # Reset to avoid affecting other tests
        logging.getLogger("agentspan").setLevel(logging.INFO)


class TestAgentConfigCredentialFields:
    """credential_strict_mode and api_key fields."""

    def test_credential_strict_mode_defaults_false(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig()
        assert config.credential_strict_mode is False

    def test_credential_strict_mode_can_be_set(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(credential_strict_mode=True)
        assert config.credential_strict_mode is True

    def test_credential_strict_mode_from_env_true(self):
        import os
        from unittest import mock
        from agentspan.agents.runtime.config import AgentConfig
        with mock.patch.dict(os.environ, {"AGENTSPAN_CREDENTIAL_STRICT_MODE": "true"}):
            config = AgentConfig.from_env()
        assert config.credential_strict_mode is True

    def test_credential_strict_mode_from_env_false(self):
        import os
        from unittest import mock
        from agentspan.agents.runtime.config import AgentConfig
        with mock.patch.dict(os.environ, {"AGENTSPAN_CREDENTIAL_STRICT_MODE": "false"}):
            config = AgentConfig.from_env()
        assert config.credential_strict_mode is False

    def test_api_key_field_defaults_none(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig()
        # api_key field (new) takes precedence; auth_key kept for backward compat
        assert config.api_key is None

    def test_api_key_field_can_be_set(self):
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(api_key="asp_my_key")
        assert config.api_key == "asp_my_key"

    def test_api_key_from_env(self):
        import os
        from unittest import mock
        from agentspan.agents.runtime.config import AgentConfig
        with mock.patch.dict(os.environ, {"AGENTSPAN_API_KEY": "asp_env_key"}):
            config = AgentConfig.from_env()
        assert config.api_key == "asp_env_key"

    def test_auth_key_backward_compat_still_works(self):
        """auth_key must still be accepted for backward compat."""
        from agentspan.agents.runtime.config import AgentConfig
        config = AgentConfig(auth_key="old_key")
        assert config.auth_key == "old_key"
