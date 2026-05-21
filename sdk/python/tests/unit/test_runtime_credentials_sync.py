# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for the credentials-API fallback used by auto-register & env hot-reload.

Context: the local Agentspan OSS server does not expose the Orkes
``/api/integrations/provider/*`` endpoints, so the original auto-register
escape hatch silently no-oped against a localhost server. The runtime now
falls back to ``PUT /api/credentials/{name}`` (the Agentspan-native credential
store) whenever the integration API call fails, and also pushes known provider
env vars into the store on boot when targeting localhost.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── helpers ────────────────────────────────────────────────────────────


def _make_runtime(*, server_url: str = "http://localhost:6767/api", auto_register: bool = False):
    """Construct an AgentRuntime with heavy I/O mocked out."""
    with (
        patch("conductor.client.orkes_clients.OrkesClients"),
        patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True),
        patch("agentspan.agents.runtime.server.ensure_server_running"),
        patch("agentspan.agents.runtime.server._is_server_ready", return_value=True),
    ):
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.runtime import AgentRuntime

        config = AgentConfig(
            server_url=server_url,
            auto_start_workers=False,
            auto_start_server=False,
            auto_register_integrations=auto_register,
        )
        return AgentRuntime(config=config)


def _api_exception(status: int, reason: str = ""):
    """Build a conductor ApiException with the given status code."""
    from conductor.client.http.rest import ApiException

    exc = ApiException(status=status, reason=reason or f"status {status}")
    return exc


# ── Fix 1: credentials API fallback for _ensure_model ─────────────────


class TestEnsureModelCredentialsFallback:
    """When the integration API returns 404 (OSS Conductor), _ensure_model must
    fall back to pushing the provider API key via /api/credentials/{name}."""

    def test_falls_back_to_credentials_on_integration_api_404(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-real-key")
        rt = _make_runtime(auto_register=True)

        # Integration API raises 404 (mimics OSS Conductor)
        fake_integration_client = MagicMock()
        fake_integration_client.save_integration.side_effect = _api_exception(404, "Not Found")
        rt._integration_client_instance = fake_integration_client

        pushed = []
        rt._push_credential_to_server = lambda name, value: pushed.append((name, value))

        rt._ensure_model("anthropic/claude-3-5-sonnet")

        # Integration API was tried, then credentials fallback used.
        assert fake_integration_client.save_integration.called
        assert pushed == [("ANTHROPIC_API_KEY", "sk-ant-test-real-key")]

    def test_skips_fallback_when_integration_api_succeeds(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        rt = _make_runtime(auto_register=True)

        fake_integration_client = MagicMock()
        # save_integration returns successfully
        rt._integration_client_instance = fake_integration_client

        pushed = []
        rt._push_credential_to_server = lambda name, value: pushed.append((name, value))

        rt._ensure_model("anthropic/claude-3-5-sonnet")

        assert fake_integration_client.save_integration.called
        assert fake_integration_client.save_integration_api.called
        # Credentials fallback NOT invoked when the integration API works.
        assert pushed == []

    def test_no_push_when_api_key_env_missing(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        rt = _make_runtime(auto_register=True)

        fake_integration_client = MagicMock()
        rt._integration_client_instance = fake_integration_client

        pushed = []
        rt._push_credential_to_server = lambda name, value: pushed.append((name, value))

        rt._ensure_model("anthropic/claude-3-5-sonnet")

        # Without an env var there is nothing to push.
        assert not fake_integration_client.save_integration.called
        assert pushed == []

    def test_does_not_push_blank_key(self, monkeypatch):
        # An empty string env var (e.g. the .zshrc typo case) must not be
        # forwarded to the server — that's exactly the bug we're protecting against.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        rt = _make_runtime(auto_register=True)

        fake_integration_client = MagicMock()
        rt._integration_client_instance = fake_integration_client

        pushed = []
        rt._push_credential_to_server = lambda name, value: pushed.append((name, value))

        rt._ensure_model("anthropic/claude-3-5-sonnet")

        assert not fake_integration_client.save_integration.called
        assert pushed == []


# ── Fix 2: hot-reload env vars on AgentRuntime boot (localhost) ───────


class TestBootEnvCredentialSync:
    """When targeting a localhost server, AgentRuntime should sync provider
    env vars into the server's credential store on construction so the running
    JVM picks up a corrected ANTHROPIC_API_KEY without a restart."""

    def test_localhost_sync_pushes_env_vars(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fresh")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fresh")
        # Make sure other known vars are unset so they don't leak in from CI env.
        for v in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY"):
            monkeypatch.delenv(v, raising=False)

        pushed = {}

        def fake_push(name, value):
            pushed[name] = value

        with patch.object(
            __import__("agentspan.agents.runtime.runtime", fromlist=["AgentRuntime"]).AgentRuntime,
            "_push_credential_to_server",
            new=lambda self, name, value: fake_push(name, value),
        ):
            _make_runtime(server_url="http://localhost:6767/api")

        assert pushed.get("ANTHROPIC_API_KEY") == "sk-ant-fresh"
        assert pushed.get("OPENAI_API_KEY") == "sk-openai-fresh"

    def test_remote_server_does_not_auto_sync(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fresh")

        pushed = {}

        def fake_push(name, value):
            pushed[name] = value

        with patch.object(
            __import__("agentspan.agents.runtime.runtime", fromlist=["AgentRuntime"]).AgentRuntime,
            "_push_credential_to_server",
            new=lambda self, name, value: fake_push(name, value),
        ):
            _make_runtime(server_url="https://hosted.example.com/api")

        # Remote: never auto-clobber UI-managed credentials.
        assert pushed == {}

    def test_blank_env_vars_skipped(self, monkeypatch):
        # The exact reproducer of the .zshrc-typo bug: env var is exported but empty.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fresh")

        pushed = {}

        def fake_push(name, value):
            pushed[name] = value

        with patch.object(
            __import__("agentspan.agents.runtime.runtime", fromlist=["AgentRuntime"]).AgentRuntime,
            "_push_credential_to_server",
            new=lambda self, name, value: fake_push(name, value),
        ):
            _make_runtime(server_url="http://127.0.0.1:6767/api")

        assert "ANTHROPIC_API_KEY" not in pushed
        assert pushed.get("OPENAI_API_KEY") == "sk-openai-fresh"


# ── _push_credential_to_server itself ─────────────────────────────────


class TestPushCredentialToServer:
    """The HTTP method/URL/headers used to push a credential."""

    def test_calls_put_credentials_endpoint(self, monkeypatch):
        rt = _make_runtime(server_url="http://localhost:6767/api")

        captured = {}

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                return None

        def fake_put(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers or {}
            return FakeResp()

        with patch("httpx.put", side_effect=fake_put):
            rt._push_credential_to_server("ANTHROPIC_API_KEY", "sk-ant-xyz")

        assert captured["url"].endswith("/api/credentials/ANTHROPIC_API_KEY")
        assert captured["json"] == {"value": "sk-ant-xyz"}

    def test_sends_auth_header_when_api_key_configured(self):
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.runtime import AgentRuntime

        with (
            patch("conductor.client.orkes_clients.OrkesClients"),
            patch("agentspan.agents.runtime.worker_manager.TaskHandler", create=True),
            patch("agentspan.agents.runtime.server.ensure_server_running"),
        ):
            cfg = AgentConfig(
                server_url="http://localhost:6767/api",
                api_key="bearer-token-abc",
                auto_start_workers=False,
                auto_start_server=False,
            )
            rt = AgentRuntime(config=cfg)

        captured = {}

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                return None

        def fake_put(url, json=None, headers=None, timeout=None):
            captured["headers"] = headers or {}
            return FakeResp()

        with patch("httpx.put", side_effect=fake_put):
            rt._push_credential_to_server("OPENAI_API_KEY", "sk-x")

        assert captured["headers"].get("Authorization") == "Bearer bearer-token-abc"
