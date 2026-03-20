# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.
import dataclasses
import pytest
from agentspan.agents.frameworks.claude import ClaudeCodeAgent, serialize_claude


class TestClaudeCodeAgent:
    def test_default_values(self):
        agent = ClaudeCodeAgent()
        assert agent.name == "claude_agent"
        assert agent.cwd == "."
        assert agent.allowed_tools == []
        assert agent.max_turns == 100
        assert agent.model == "claude-opus-4-6"
        assert agent.max_tokens == 8192
        assert agent.system_prompt is None
        assert agent.conductor_subagents is False
        assert agent.agentspan_routing is False
        assert agent.subagent_overrides == {}
        assert agent.prompt == ""

    def test_custom_values(self):
        agent = ClaudeCodeAgent(
            name="my_agent",
            cwd="/tmp/project",
            allowed_tools=["Read", "Bash"],
            max_turns=50,
            conductor_subagents=True,
        )
        assert agent.name == "my_agent"
        assert agent.cwd == "/tmp/project"
        assert agent.allowed_tools == ["Read", "Bash"]
        assert agent.conductor_subagents is True

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(ClaudeCodeAgent)


class TestSerializeClaude:
    def test_returns_tuple(self):
        agent = ClaudeCodeAgent(name="test_agent")
        raw_config, workers = serialize_claude(agent)
        assert isinstance(raw_config, dict)
        assert isinstance(workers, list)
        assert len(workers) == 1

    def test_worker_name_has_fw_prefix(self):
        agent = ClaudeCodeAgent(name="my_agent")
        raw_config, workers = serialize_claude(agent)
        assert workers[0].name == "_fw_claude_my_agent"
        assert raw_config["_worker_name"] == "_fw_claude_my_agent"

    def test_raw_config_contains_all_fields(self):
        agent = ClaudeCodeAgent(
            name="test",
            cwd="/workspace",
            allowed_tools=["Read", "Write"],
            max_turns=50,
            model="claude-sonnet-4-6",
            conductor_subagents=True,
            agentspan_routing=False,
        )
        raw_config, _ = serialize_claude(agent)
        assert raw_config["cwd"] == "/workspace"
        assert raw_config["allowed_tools"] == ["Read", "Write"]
        assert raw_config["max_turns"] == 50
        assert raw_config["model"] == "claude-sonnet-4-6"
        assert raw_config["conductor_subagents"] is True
        assert raw_config["agentspan_routing"] is False
        assert raw_config["max_tokens"] == 8192  # default since not overridden
        assert raw_config["system_prompt"] is None  # default
        assert raw_config["subagent_overrides"] == {}  # default

    def test_worker_func_is_none(self):
        """serialize_claude returns func=None — filled by _build_passthrough_func."""
        agent = ClaudeCodeAgent(name="test")
        _, workers = serialize_claude(agent)
        assert workers[0].func is None
