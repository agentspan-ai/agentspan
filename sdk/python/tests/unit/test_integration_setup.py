# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for LLM integration auto-registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentspan.agents._internal.provider_registry import (
    PROVIDER_REGISTRY,
    ProviderSpec,
    get_provider_spec,
)


# ── Provider Registry ───────────────────────────────────────────────────


class TestProviderRegistry:
    """Test the provider registry data and lookup."""

    def test_known_providers_have_entries(self):
        """The three main providers should be in the registry."""
        assert "openai" in PROVIDER_REGISTRY
        assert "anthropic" in PROVIDER_REGISTRY
        assert "google_gemini" in PROVIDER_REGISTRY

    def test_openai_spec(self):
        spec = PROVIDER_REGISTRY["openai"]
        assert spec.name == "openai"
        assert spec.integration_type == "openai"
        assert spec.display_name == "OpenAI"
        assert spec.api_key_env == "OPENAI_API_KEY"

    def test_anthropic_spec(self):
        spec = PROVIDER_REGISTRY["anthropic"]
        assert spec.name == "anthropic"
        assert spec.api_key_env == "ANTHROPIC_API_KEY"

    def test_google_gemini_spec(self):
        spec = PROVIDER_REGISTRY["google_gemini"]
        assert spec.name == "google_gemini"
        assert spec.api_key_env == "GOOGLE_GEMINI_API_KEY"

    def test_get_provider_spec_known(self):
        spec = get_provider_spec("openai")
        assert spec is not None
        assert spec.name == "openai"

    def test_get_provider_spec_unknown(self):
        assert get_provider_spec("nonexistent") is None

    def test_provider_spec_is_frozen(self):
        spec = PROVIDER_REGISTRY["openai"]
        with pytest.raises(AttributeError):
            spec.name = "changed"


# ── Auto-Registration Logic ─────────────────────────────────────────────


class TestEnsureModel:
    """Test _ensure_model() on AgentRuntime with mocked IntegrationClient."""

    def _make_runtime(self, auto_register=True):
        """Create an AgentRuntime with mocked Conductor clients."""
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients, \
             patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):

            mock_clients = MagicMock()
            MockClients.return_value = mock_clients

            mock_integration_client = MagicMock()
            mock_clients.get_integration_client.return_value = mock_integration_client

            from agentspan.agents.runtime.config import AgentConfig
            from agentspan.agents.runtime.runtime import AgentRuntime

            config = AgentConfig(
                server_url="http://localhost:8080/api",
                auto_register_integrations=auto_register,
            )
            runtime = AgentRuntime(config=config)
            return runtime, mock_integration_client

    def test_upserts_integration_with_api_key(self):
        """Always upserts integration with correct API key and enabled=True."""
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            runtime._ensure_model("openai/gpt-4o")

        mock_client.save_integration.assert_called_once()
        call_args = mock_client.save_integration.call_args
        assert call_args[0][0] == "openai"
        integration_update = call_args[0][1]
        assert integration_update.type == "openai"
        assert integration_update.category == "AI_MODEL"
        assert integration_update.configuration == {"api_key": "sk-test123"}
        assert integration_update.enabled is True

    def test_upserts_model_with_enabled(self):
        """Always upserts model with enabled=True."""
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            runtime._ensure_model("openai/gpt-4o")

        mock_client.save_integration_api.assert_called_once()
        call_args = mock_client.save_integration_api.call_args
        assert call_args[0][0] == "openai"
        assert call_args[0][1] == "gpt-4o"
        api_update = call_args[0][2]
        assert api_update.enabled is True

    def test_caches_to_avoid_repeat_upserts(self):
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            runtime._ensure_model("openai/gpt-4o")
            runtime._ensure_model("openai/gpt-4o")  # second call

        # save_integration should only be called once (cached on second call)
        assert mock_client.save_integration.call_count == 1

    def test_skips_unknown_provider(self):
        runtime, mock_client = self._make_runtime()

        runtime._ensure_model("unknown_provider/some-model")

        mock_client.get_integration.assert_not_called()
        assert "unknown_provider/some-model" in runtime._ensured_models

    def test_skips_when_api_key_not_set(self):
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {}, clear=True):
            runtime._ensure_model("openai/gpt-4o")

        mock_client.get_integration.assert_not_called()
        assert "openai/gpt-4o" in runtime._ensured_models

    def test_anthropic_integration(self):
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            runtime._ensure_model("anthropic/claude-sonnet-4-20250514")

        call_args = mock_client.save_integration.call_args
        assert call_args[0][0] == "anthropic"
        integration_update = call_args[0][1]
        assert integration_update.type == "anthropic"
        assert integration_update.configuration == {"api_key": "sk-ant-test"}
        assert integration_update.enabled is True

        model_args = mock_client.save_integration_api.call_args
        assert model_args[0][0] == "anthropic"
        assert model_args[0][1] == "claude-sonnet-4-20250514"

    def test_google_gemini_integration(self):
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"GOOGLE_GEMINI_API_KEY": "AIza-test"}):
            runtime._ensure_model("google_gemini/gemini-2.0-flash")

        call_args = mock_client.save_integration.call_args
        assert call_args[0][0] == "google_gemini"
        assert call_args[0][1].type == "google_gemini"
        assert call_args[0][1].enabled is True

    def test_handles_api_exception_gracefully(self):
        runtime, mock_client = self._make_runtime()
        mock_client.save_integration.side_effect = Exception("Connection refused")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            # Should not raise — just log a warning
            runtime._ensure_model("openai/gpt-4o")

        assert "openai/gpt-4o" in runtime._ensured_models

    def test_disables_after_first_failure_oss(self):
        """On OSS Conductor (no integration API), first failure disables further attempts."""
        runtime, mock_client = self._make_runtime()
        mock_client.save_integration.side_effect = Exception("404 Not Found")

        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "sk-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }):
            runtime._ensure_model("openai/gpt-4o")
            runtime._ensure_model("anthropic/claude-sonnet-4-20250514")

        # First call hits the API and fails
        assert mock_client.save_integration.call_count == 1
        # After first failure, _integration_api_available is False — second call short-circuits
        assert runtime._integration_api_available is False
        # First model is in ensured (attempted), second is silently skipped (no-op)
        assert "openai/gpt-4o" in runtime._ensured_models

    def test_marks_available_on_success(self):
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            runtime._ensure_model("openai/gpt-4o")

        assert runtime._integration_api_available is True

    def test_subsequent_failure_after_success_still_tries(self):
        """If API was available before, a later failure is per-model, not a global disable."""
        runtime, mock_client = self._make_runtime()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            runtime._ensure_model("openai/gpt-4o")

        assert runtime._integration_api_available is True

        # Second call fails on save
        mock_client.save_integration.side_effect = Exception("Transient error")

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            runtime._ensure_model("anthropic/claude-sonnet-4-20250514")

        # Should still be marked available (not disabled globally)
        assert runtime._integration_api_available is True


class TestEnsureModelsForAgent:
    """Test _ensure_models_for_agent() tree walking."""

    def _make_runtime(self):
        """Create an AgentRuntime with mocked clients."""
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients, \
             patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):

            mock_clients = MagicMock()
            MockClients.return_value = mock_clients
            mock_integration_client = MagicMock()
            mock_clients.get_integration_client.return_value = mock_integration_client

            from agentspan.agents.runtime.config import AgentConfig
            from agentspan.agents.runtime.runtime import AgentRuntime

            config = AgentConfig(
                server_url="http://localhost:8080/api",
                auto_register_integrations=True,
            )
            runtime = AgentRuntime(config=config)
            return runtime, mock_integration_client

    def test_single_agent(self):
        from agentspan.agents.agent import Agent

        runtime, mock_client = self._make_runtime()

        agent = Agent(name="test", model="openai/gpt-4o")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            runtime._ensure_models_for_agent(agent)

        assert "openai/gpt-4o" in runtime._ensured_models
        mock_client.save_integration.assert_called_once()

    def test_multi_agent_tree(self):
        from agentspan.agents.agent import Agent

        runtime, mock_client = self._make_runtime()

        sub1 = Agent(name="sub1", model="openai/gpt-4o")
        sub2 = Agent(name="sub2", model="anthropic/claude-sonnet-4-20250514")
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[sub1, sub2],
            strategy="handoff",
        )

        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "sk-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }):
            runtime._ensure_models_for_agent(parent)

        assert "openai/gpt-4o" in runtime._ensured_models
        assert "anthropic/claude-sonnet-4-20250514" in runtime._ensured_models

    def test_deduplicates_same_model(self):
        from agentspan.agents.agent import Agent

        runtime, mock_client = self._make_runtime()

        sub1 = Agent(name="sub1", model="openai/gpt-4o")
        sub2 = Agent(name="sub2", model="openai/gpt-4o")
        parent = Agent(
            name="parent",
            model="openai/gpt-4o",
            agents=[sub1, sub2],
            strategy="handoff",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            runtime._ensure_models_for_agent(parent)

        # save_integration should only be called once despite 3 agents with same model
        assert mock_client.save_integration.call_count == 1


class TestAutoRegisterInPrepare:
    """Test that _prepare() calls auto-registration when enabled."""

    def test_prepare_calls_ensure_when_enabled(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients, \
             patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):

            mock_clients = MagicMock()
            MockClients.return_value = mock_clients

            from agentspan.agents.agent import Agent
            from agentspan.agents.runtime.config import AgentConfig
            from agentspan.agents.runtime.runtime import AgentRuntime

            config = AgentConfig(
                server_url="http://localhost:8080/api",
                auto_register_integrations=True,
            )
            runtime = AgentRuntime(config=config)
            runtime._ensure_models_for_agent = MagicMock()
            runtime._compile_agent = MagicMock()

            agent = Agent(name="test", model="openai/gpt-4o")
            runtime._prepare(agent)

            runtime._ensure_models_for_agent.assert_called_once_with(agent)

    def test_prepare_skips_ensure_when_disabled(self):
        with patch("conductor.client.orkes_clients.OrkesClients") as MockClients, \
             patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True):

            mock_clients = MagicMock()
            MockClients.return_value = mock_clients

            from agentspan.agents.agent import Agent
            from agentspan.agents.runtime.config import AgentConfig
            from agentspan.agents.runtime.runtime import AgentRuntime

            config = AgentConfig(
                server_url="http://localhost:8080/api",
                auto_register_integrations=False,
            )
            runtime = AgentRuntime(config=config)
            runtime._ensure_models_for_agent = MagicMock()
            runtime._compile_agent = MagicMock()

            agent = Agent(name="test", model="openai/gpt-4o")
            runtime._prepare(agent)

            runtime._ensure_models_for_agent.assert_not_called()


class TestAgentConfigAutoRegister:
    """Test the auto_register_integrations config field."""

    def test_default_is_false(self):
        from agentspan.agents.runtime.config import AgentConfig

        config = AgentConfig()
        assert config.auto_register_integrations is False

    def test_env_reads_flag(self):
        from agentspan.agents.runtime.config import AgentConfig

        with patch.dict("os.environ", {"AGENTSPAN_INTEGRATIONS_AUTO_REGISTER": "true"}):
            config = AgentConfig()
            assert config.auto_register_integrations is True

    def test_false_by_default(self):
        from agentspan.agents.runtime.config import AgentConfig

        with patch.dict("os.environ", {}, clear=True):
            config = AgentConfig()
            assert config.auto_register_integrations is False

    def test_various_truthy_values(self):
        from agentspan.agents.runtime.config import AgentConfig

        for val in ("true", "True", "TRUE", "1", "yes"):
            with patch.dict("os.environ", {"AGENTSPAN_INTEGRATIONS_AUTO_REGISTER": val}):
                config = AgentConfig()
                assert config.auto_register_integrations is True, f"Failed for {val!r}"
