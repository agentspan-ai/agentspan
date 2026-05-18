"""Unit tests for build_resolved_env()."""

from __future__ import annotations

import os

from validation.execution.runner import build_resolved_env


class TestBuildResolvedEnv:
    def test_llm_model_always_set(self):
        env = build_resolved_env("openai/gpt-4o", None)
        assert env["AGENTSPAN_LLM_MODEL"] == "openai/gpt-4o"

    def test_server_url_set_when_provided(self):
        env = build_resolved_env("openai/gpt-4o", "http://localhost:6767/api")
        assert env["AGENTSPAN_SERVER_URL"] == "http://localhost:6767/api"

    def test_server_url_absent_when_none(self):
        env = build_resolved_env("openai/gpt-4o", None)
        assert "AGENTSPAN_SERVER_URL" not in env

    def test_secondary_model_optional(self):
        env_without = build_resolved_env("openai/gpt-4o", None)
        assert "AGENTSPAN_SECONDARY_LLM_MODEL" not in env_without

        env_with = build_resolved_env("openai/gpt-4o", None, secondary_model="anthropic/claude-3")
        assert env_with["AGENTSPAN_SECONDARY_LLM_MODEL"] == "anthropic/claude-3"

    def test_run_env_overrides_global_env(self):
        env = build_resolved_env(
            "openai/gpt-4o",
            None,
            global_env={"MY_VAR": "global"},
            run_env={"MY_VAR": "run"},
        )
        assert env["MY_VAR"] == "run"

    def test_global_env_overrides_shell(self, monkeypatch):
        monkeypatch.setenv("MY_SHELL_VAR", "shell")
        env = build_resolved_env("openai/gpt-4o", None, global_env={"MY_SHELL_VAR": "global"})
        assert env["MY_SHELL_VAR"] == "global"

    def test_two_runs_are_independent(self):
        env_a = build_resolved_env("openai/gpt-4o", "http://localhost:8081/api")
        env_b = build_resolved_env("anthropic/claude-3", "http://localhost:8082/api")
        assert env_a is not env_b
        assert env_a["AGENTSPAN_LLM_MODEL"] != env_b["AGENTSPAN_LLM_MODEL"]
        assert env_a["AGENTSPAN_SERVER_URL"] != env_b["AGENTSPAN_SERVER_URL"]

    def test_os_environ_not_mutated(self):
        before = dict(os.environ)
        build_resolved_env("openai/gpt-4o", "http://localhost:6767/api", secondary_model="m2")
        assert dict(os.environ) == before
        assert "AGENTSPAN_LLM_MODEL" not in os.environ or os.environ.get(
            "AGENTSPAN_LLM_MODEL"
        ) == before.get("AGENTSPAN_LLM_MODEL")
