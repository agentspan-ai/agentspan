"""Tests for agent loader."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from autopilot.loader import LoaderError, load_agent


def _write_yaml(agent_dir: Path, data: dict) -> None:
    (agent_dir / "agent.yaml").write_text(yaml.dump(data))


def _write_worker(agent_dir: Path, name: str, code: str) -> None:
    workers_dir = agent_dir / "workers"
    workers_dir.mkdir(exist_ok=True)
    (workers_dir / f"{name}.py").write_text(dedent(code))


class TestBasicLoad:
    def test_loads_agent_with_name_and_model(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "my_agent",
            "model": "openai/gpt-4o",
            "instructions": "You are helpful.",
        })

        agent = load_agent(tmp_agent_dir)

        assert agent.name == "my_agent"
        assert agent.model == "openai/gpt-4o"
        assert "helpful" in agent.instructions

    def test_loads_worker_tools(self, tmp_agent_dir: Path):
        _write_worker(tmp_agent_dir, "greet", """\
            from agentspan.agents import tool

            @tool
            def greet(name: str) -> str:
                \"\"\"Say hello.\"\"\"
                return f"Hello, {name}!"
        """)
        _write_yaml(tmp_agent_dir, {
            "name": "greeter",
            "model": "openai/gpt-4o",
            "tools": ["greet"],
        })

        agent = load_agent(tmp_agent_dir)

        assert len(agent.tools) == 1
        assert agent.tools[0]._tool_def.name == "greet"

    def test_no_tools_produces_empty_list(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "bare_agent",
            "model": "openai/gpt-4o",
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.tools == []


class TestCredentials:
    def test_credentials_loaded_from_yaml(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "cred_agent",
            "model": "openai/gpt-4o",
            "credentials": ["API_KEY", "SECRET"],
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.credentials == ["API_KEY", "SECRET"]


class TestTrigger:
    def test_trigger_stored_in_metadata(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "triggered",
            "model": "openai/gpt-4o",
            "trigger": {"type": "cron", "schedule": "0 * * * *"},
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.metadata["trigger"] == {"type": "cron", "schedule": "0 * * * *"}


class TestStateful:
    def test_stateful_flag(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "stateful_agent",
            "model": "openai/gpt-4o",
            "stateful": True,
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.stateful is True


class TestErrorHandling:
    def test_error_handling_in_metadata(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "resilient",
            "model": "openai/gpt-4o",
            "error_handling": {"retry": 3, "fallback": "default"},
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.metadata["error_handling"] == {"retry": 3, "fallback": "default"}


class TestIntegrationTools:
    def test_builtin_local_fs(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "fs_agent",
            "model": "openai/gpt-4o",
            "tools": ["builtin:local_fs"],
        })

        agent = load_agent(tmp_agent_dir)

        tool_names = [t._tool_def.name for t in agent.tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_dir" in tool_names

    def test_unknown_builtin_raises(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "bad_builtin",
            "model": "openai/gpt-4o",
            "tools": ["builtin:nonexistent"],
        })

        with pytest.raises(LoaderError, match="No tools found"):
            load_agent(tmp_agent_dir)


class TestValidationErrors:
    def test_missing_yaml_raises(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(LoaderError, match="agent.yaml not found"):
            load_agent(empty_dir)

    def test_missing_name_raises(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "model": "openai/gpt-4o",
        })

        with pytest.raises(LoaderError, match="missing required 'name'"):
            load_agent(tmp_agent_dir)

    def test_missing_worker_file_raises(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "broken",
            "model": "openai/gpt-4o",
            "tools": ["nonexistent_tool"],
        })

        with pytest.raises(LoaderError, match="Worker file not found"):
            load_agent(tmp_agent_dir)

    def test_invalid_yaml_raises(self, tmp_agent_dir: Path):
        (tmp_agent_dir / "agent.yaml").write_text("}{not valid yaml")

        with pytest.raises(LoaderError, match="Invalid YAML"):
            load_agent(tmp_agent_dir)

    def test_malformed_worker_no_tool_decorator(self, tmp_agent_dir: Path):
        _write_worker(tmp_agent_dir, "bad_worker", """\
            def not_a_tool(x: int) -> int:
                return x + 1
        """)
        _write_yaml(tmp_agent_dir, {
            "name": "malformed",
            "model": "openai/gpt-4o",
            "tools": ["bad_worker"],
        })

        with pytest.raises(LoaderError, match="No @tool-decorated"):
            load_agent(tmp_agent_dir)


class TestVersionAndIntegrations:
    def test_version_in_metadata(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "versioned",
            "model": "openai/gpt-4o",
            "version": "1.2.3",
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.metadata["version"] == "1.2.3"

    def test_integrations_in_metadata(self, tmp_agent_dir: Path):
        _write_yaml(tmp_agent_dir, {
            "name": "integrated",
            "model": "openai/gpt-4o",
            "integrations": ["slack", "github"],
        })

        agent = load_agent(tmp_agent_dir)
        assert agent.metadata["integrations"] == ["slack", "github"]


class TestUniqueModuleNames:
    def test_two_agents_same_tool_name_no_collision(self, tmp_path: Path):
        """Two agent dirs with workers/greet.py should load independently."""
        # Agent A
        dir_a = tmp_path / "agent_a"
        dir_a.mkdir()
        (dir_a / "workers").mkdir()
        _write_yaml(dir_a, {
            "name": "agent_a",
            "model": "openai/gpt-4o",
            "tools": ["greet"],
        })
        _write_worker(dir_a, "greet", """\
            from agentspan.agents import tool

            @tool
            def greet(name: str) -> str:
                \"\"\"Greet from A.\"\"\"
                return f"A says hi, {name}!"
        """)

        # Agent B
        dir_b = tmp_path / "agent_b"
        dir_b.mkdir()
        (dir_b / "workers").mkdir()
        _write_yaml(dir_b, {
            "name": "agent_b",
            "model": "openai/gpt-4o",
            "tools": ["greet"],
        })
        _write_worker(dir_b, "greet", """\
            from agentspan.agents import tool

            @tool
            def greet(name: str) -> str:
                \"\"\"Greet from B.\"\"\"
                return f"B says hi, {name}!"
        """)

        agent_a = load_agent(dir_a)
        agent_b = load_agent(dir_b)

        # Both load successfully with their own tool
        assert agent_a.tools[0]("World") == "A says hi, World!"
        assert agent_b.tools[0]("World") == "B says hi, World!"
