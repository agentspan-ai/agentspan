"""Tests for orchestrator tools — all use real files via tmp_path, no mocks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from autopilot.orchestrator.state import AgentState, StateManager
from autopilot.orchestrator.tools import (
    OrchestratorError,
    check_credentials,
    commit_agent_change,
    expand_prompt,
    generate_agent,
    generate_worker,
    get_agent_status,
    get_notifications,
    init_autopilot_repo,
    list_agents,
    resolve_integrations,
    signal_agent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_agent_yaml(agents_dir: Path, name: str, data: dict) -> Path:
    """Create an agent directory with agent.yaml."""
    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "workers").mkdir(exist_ok=True)
    (agent_dir / "agent.yaml").write_text(yaml.dump(data, default_flow_style=False))
    return agent_dir


def _make_config_env(monkeypatch, tmp_path: Path) -> Path:
    """Configure the autopilot to use tmp_path as the base directory.

    Returns the agents directory path.
    """
    monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


# ---------------------------------------------------------------------------
# expand_prompt
# ---------------------------------------------------------------------------

class TestExpandPrompt:
    def test_returns_template_with_seed_prompt(self):
        result = expand_prompt("scan my emails every morning")
        assert "scan my emails every morning" in result

    def test_includes_clarifications_when_provided(self):
        result = expand_prompt("monitor github", clarifications="Only the main repo")
        assert "Only the main repo" in result

    def test_includes_none_provided_when_no_clarifications(self):
        result = expand_prompt("do something")
        assert "None provided" in result

    def test_includes_yaml_field_names(self):
        result = expand_prompt("build a bot")
        assert "name:" in result
        assert "version:" in result
        assert "model:" in result
        assert "instructions:" in result
        assert "trigger:" in result
        assert "tools:" in result
        assert "credentials:" in result
        assert "error_handling:" in result

    def test_lists_available_integrations(self):
        result = expand_prompt("anything")
        # The registry should have at least local_fs registered
        assert "local_fs" in result


# ---------------------------------------------------------------------------
# generate_agent
# ---------------------------------------------------------------------------

class TestGenerateAgent:
    def test_creates_agent_directory(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        spec = yaml.dump({
            "name": "test_gen",
            "model": "openai/gpt-4o",
            "instructions": "You are a test agent.",
            "trigger": {"type": "daemon"},
        })

        result = generate_agent(spec, "test_gen")

        assert "test_gen" in result
        assert "created successfully" in result
        assert (agents_dir / "test_gen" / "agent.yaml").exists()
        assert (agents_dir / "test_gen" / "expanded_prompt.md").exists()
        assert (agents_dir / "test_gen" / "workers").is_dir()

    def test_writes_valid_agent_yaml(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        spec = yaml.dump({
            "name": "yaml_check",
            "model": "anthropic/claude-sonnet-4-20250514",
            "instructions": "Summarize things.",
            "trigger": {"type": "cron", "schedule": "0 8 * * *"},
            "credentials": ["API_KEY"],
        })

        generate_agent(spec, "yaml_check")

        written = yaml.safe_load((agents_dir / "yaml_check" / "agent.yaml").read_text())
        assert written["name"] == "yaml_check"
        # Model is forced to the configured default (prevents LLM from picking cheap models)
        assert written["model"] is not None
        assert written["credentials"] == ["API_KEY"]
        assert written["trigger"]["type"] == "cron"

    def test_writes_expanded_prompt(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        spec = yaml.dump({
            "name": "prompt_check",
            "instructions": "Do the thing well.",
        })

        generate_agent(spec, "prompt_check")

        prompt_text = (agents_dir / "prompt_check" / "expanded_prompt.md").read_text()
        assert "prompt_check" in prompt_text
        assert "Do the thing well." in prompt_text

    def test_registers_draft_state(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)

        spec = yaml.dump({"name": "draft_check", "trigger": {"type": "cron"}})
        generate_agent(spec, "draft_check")

        sm = StateManager(tmp_path / "state.json")
        state = sm.get("draft_check")
        assert state is not None
        assert state.status == "DRAFT"
        assert state.trigger_type == "cron"

    def test_invalid_yaml_returns_error(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)
        result = generate_agent("}{not valid yaml", "bad_agent")
        assert "Error" in result

    def test_empty_spec_returns_error(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)
        # YAML that parses to a string, not a dict
        result = generate_agent("just a string", "bad")
        assert "Error" in result


# ---------------------------------------------------------------------------
# list_agents
# ---------------------------------------------------------------------------

class TestListAgents:
    def test_no_agents_dir(self, monkeypatch, tmp_path: Path):
        # Point to a dir that doesn't have agents/ subdir
        monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path / "empty"))
        result = list_agents()
        assert "No agents" in result

    def test_lists_real_agents(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "alpha_agent", {
            "name": "alpha_agent",
            "model": "openai/gpt-4o",
        })
        _write_agent_yaml(agents_dir, "beta_agent", {
            "name": "beta_agent",
            "model": "openai/gpt-4o",
        })

        result = list_agents()
        assert "alpha_agent" in result
        assert "beta_agent" in result

    def test_shows_status_from_state(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "stateful", {
            "name": "stateful",
            "model": "openai/gpt-4o",
        })

        sm = StateManager(tmp_path / "state.json")
        sm.set("stateful", AgentState(
            name="stateful",
            execution_id="exec-123",
            status="ACTIVE",
            trigger_type="daemon",
            created_at="2026-04-12T00:00:00Z",
        ))

        result = list_agents()
        assert "ACTIVE" in result

    def test_untracked_agent_shown(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "untracked", {
            "name": "untracked",
            "model": "openai/gpt-4o",
        })
        # No state set for this agent

        result = list_agents()
        assert "untracked" in result
        assert "UNTRACKED" in result

    def test_ignores_dirs_without_agent_yaml(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        # Create a directory without agent.yaml
        (agents_dir / "not_an_agent").mkdir()

        # Create a proper agent
        _write_agent_yaml(agents_dir, "real_agent", {
            "name": "real_agent",
            "model": "openai/gpt-4o",
        })

        result = list_agents()
        assert "real_agent" in result
        assert "not_an_agent" not in result


# ---------------------------------------------------------------------------
# resolve_integrations
# ---------------------------------------------------------------------------

class TestResolveIntegrations:
    def test_checks_builtin_integrations(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "int_check", {
            "name": "int_check",
            "model": "openai/gpt-4o",
            "tools": ["builtin:local_fs"],
        })

        result = resolve_integrations("int_check")
        assert "local_fs" in result
        assert "OK" in result

    def test_reports_missing_builtin(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "missing_int", {
            "name": "missing_int",
            "model": "openai/gpt-4o",
            "tools": ["builtin:nonexistent_service"],
        })

        result = resolve_integrations("missing_int")
        assert "MISSING" in result
        assert "nonexistent_service" in result

    def test_reports_credentials(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "cred_agent", {
            "name": "cred_agent",
            "model": "openai/gpt-4o",
            "credentials": ["GMAIL_OAUTH", "WHATSAPP_KEY"],
        })

        result = resolve_integrations("cred_agent")
        assert "GMAIL_OAUTH" in result
        assert "WHATSAPP_KEY" in result

    def test_missing_agent_returns_error(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)
        result = resolve_integrations("ghost_agent")
        assert "Error" in result
        assert "ghost_agent" in result

    def test_worker_tool_exists(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        agent_dir = _write_agent_yaml(agents_dir, "worker_agent", {
            "name": "worker_agent",
            "model": "openai/gpt-4o",
            "tools": ["my_worker"],
        })
        (agent_dir / "workers" / "my_worker.py").write_text("# placeholder")

        result = resolve_integrations("worker_agent")
        assert "my_worker" in result
        assert "worker" in result.lower()

    def test_worker_tool_missing(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "missing_worker", {
            "name": "missing_worker",
            "model": "openai/gpt-4o",
            "tools": ["nonexistent_worker"],
        })

        result = resolve_integrations("missing_worker")
        assert "MISSING" in result
        assert "nonexistent_worker" in result


# ---------------------------------------------------------------------------
# check_credentials
# ---------------------------------------------------------------------------

class TestCheckCredentials:
    def test_no_credentials_needed(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "no_creds", {
            "name": "no_creds",
            "model": "openai/gpt-4o",
        })

        result = check_credentials("no_creds")
        assert "does not require" in result

    def test_lists_required_credentials(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "needs_creds", {
            "name": "needs_creds",
            "model": "openai/gpt-4o",
            "credentials": ["STRIPE_KEY", "DB_PASSWORD"],
        })

        result = check_credentials("needs_creds")
        assert "STRIPE_KEY" in result
        assert "DB_PASSWORD" in result

    def test_missing_agent_returns_error(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)
        result = check_credentials("nonexistent")
        assert "Error" in result


# ---------------------------------------------------------------------------
# signal_agent — missing agent
# ---------------------------------------------------------------------------

class TestSignalAgentMissing:
    def test_raises_for_unknown_agent(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)

        with pytest.raises(OrchestratorError, match="not tracked"):
            signal_agent("ghost_agent", "hello")


# ---------------------------------------------------------------------------
# get_agent_status — missing agent
# ---------------------------------------------------------------------------

class TestGetAgentStatusMissing:
    def test_raises_for_unknown_agent(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)

        with pytest.raises(OrchestratorError, match="not tracked"):
            get_agent_status("ghost_agent")

    def test_returns_status_for_tracked_agent(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)

        _write_agent_yaml(agents_dir, "tracked", {
            "name": "tracked",
            "model": "openai/gpt-4o",
            "version": 2,
            "credentials": ["MY_KEY"],
        })

        sm = StateManager(tmp_path / "state.json")
        sm.set("tracked", AgentState(
            name="tracked",
            execution_id="exec-xyz",
            status="ACTIVE",
            trigger_type="cron",
            created_at="2026-04-12T00:00:00Z",
            last_deployed="2026-04-12T01:00:00Z",
        ))

        result = get_agent_status("tracked")
        assert "tracked" in result
        assert "ACTIVE" in result
        assert "cron" in result
        assert "exec-xyz" in result
        assert "Version: 2" in result
        assert "MY_KEY" in result


# ---------------------------------------------------------------------------
# get_notifications
# ---------------------------------------------------------------------------

class TestGetNotifications:
    def test_no_agents_returns_empty(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)
        result = get_notifications()
        assert "No agents" in result or "Nothing" in result

    def test_shows_error_agents(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)

        sm = StateManager(tmp_path / "state.json")
        sm.set("broken", AgentState(
            name="broken",
            execution_id="e1",
            status="ERROR",
            trigger_type="daemon",
            created_at="t",
        ))

        result = get_notifications()
        assert "ERROR" in result
        assert "broken" in result
        assert "1 errors" in result

    def test_shows_waiting_agents(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)

        sm = StateManager(tmp_path / "state.json")
        sm.set("hitl", AgentState(
            name="hitl",
            execution_id="e2",
            status="WAITING",
            trigger_type="daemon",
            created_at="t",
        ))

        result = get_notifications()
        assert "WAITING" in result
        assert "hitl" in result

    def test_summary_counts(self, monkeypatch, tmp_path: Path):
        _make_config_env(monkeypatch, tmp_path)

        sm = StateManager(tmp_path / "state.json")
        sm.set("a1", AgentState(name="a1", execution_id="e", status="ACTIVE", trigger_type="daemon", created_at="t"))
        sm.set("a2", AgentState(name="a2", execution_id="e", status="ACTIVE", trigger_type="daemon", created_at="t"))
        sm.set("w1", AgentState(name="w1", execution_id="e", status="WAITING", trigger_type="daemon", created_at="t"))
        sm.set("e1", AgentState(name="e1", execution_id="e", status="ERROR", trigger_type="daemon", created_at="t"))

        result = get_notifications()
        assert "2 active" in result
        assert "1 waiting" in result
        assert "1 errors" in result


# ---------------------------------------------------------------------------
# generate_worker
# ---------------------------------------------------------------------------


class TestGenerateWorker:
    def test_creates_worker_file(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        _write_agent_yaml(agents_dir, "my_agent", {
            "name": "my_agent",
            "model": "openai/gpt-4o",
            "tools": [],
        })

        result = generate_worker(
            agent_name="my_agent",
            tool_name="fetch_data",
            description="Fetch data from an API",
            parameters="url: str, limit: int = 10",
        )

        worker_path = agents_dir / "my_agent" / "workers" / "fetch_data.py"
        assert worker_path.exists()
        content = worker_path.read_text()
        assert "@tool" in content
        assert "def fetch_data" in content
        assert "url: str" in content
        assert "limit: int = 10" in content

    def test_updates_agent_yaml_tools(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        _write_agent_yaml(agents_dir, "my_agent", {
            "name": "my_agent",
            "model": "openai/gpt-4o",
            "tools": ["existing_tool"],
        })

        generate_worker(
            agent_name="my_agent",
            tool_name="new_tool",
            description="A new tool",
        )

        updated_yaml = yaml.safe_load((agents_dir / "my_agent" / "agent.yaml").read_text())
        assert "new_tool" in updated_yaml["tools"]
        assert "existing_tool" in updated_yaml["tools"]

    def test_creates_agent_dir_if_missing(self, monkeypatch, tmp_path: Path):
        """generate_worker creates the agent directory if it doesn't exist yet."""
        _make_config_env(monkeypatch, tmp_path)

        generate_worker(
            agent_name="new_agent",
            tool_name="my_tool",
            description="does something",
            implementation="return 'done'",
        )

        worker_path = tmp_path / "agents" / "new_agent" / "workers" / "my_tool.py"
        assert worker_path.exists()
        assert "return 'done'" in worker_path.read_text()

    def test_includes_implementation_code(self, monkeypatch, tmp_path: Path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        _write_agent_yaml(agents_dir, "math_agent", {
            "name": "math_agent",
            "model": "openai/gpt-4o",
            "tools": [],
        })

        generate_worker(
            agent_name="math_agent",
            tool_name="add_numbers",
            description="Add two numbers",
            parameters="a: int, b: int",
            implementation="result = a + b\nreturn str(result)",
        )

        content = (agents_dir / "math_agent" / "workers" / "add_numbers.py").read_text()
        assert "result = a + b" in content
        assert "return str(result)" in content
        assert "@tool" in content
        assert "NotImplementedError" not in content


# ---------------------------------------------------------------------------
# Git versioning
# ---------------------------------------------------------------------------


class TestGitVersioning:
    def test_init_autopilot_repo_creates_git(self, tmp_path: Path):
        from autopilot.config import AutopilotConfig
        config = AutopilotConfig(base_dir=tmp_path)
        init_autopilot_repo(config)
        assert (tmp_path / ".git").exists()
        assert (tmp_path / ".gitignore").exists()

    def test_init_is_idempotent(self, tmp_path: Path):
        from autopilot.config import AutopilotConfig
        config = AutopilotConfig(base_dir=tmp_path)
        init_autopilot_repo(config)
        init_autopilot_repo(config)  # Should not fail
        assert (tmp_path / ".git").exists()

    def test_commit_agent_change(self, tmp_path: Path):
        import subprocess
        from autopilot.config import AutopilotConfig
        config = AutopilotConfig(base_dir=tmp_path)
        init_autopilot_repo(config)

        # Create an agent dir
        agent_dir = tmp_path / "agents" / "test_agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.yaml").write_text("name: test_agent\n")

        commit_agent_change("test_agent", "created agent", config)

        # Verify the commit exists
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert "[test_agent] created agent" in result.stdout
