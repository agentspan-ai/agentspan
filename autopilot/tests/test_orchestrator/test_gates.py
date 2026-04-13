"""Tests for validation gates — all use real files via tmp_path, no mocks."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autopilot.orchestrator.gates import (
    run_all_gates,
    validate_code,
    validate_deployment,
    validate_integrations,
    validate_spec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config_env(monkeypatch, tmp_path: Path) -> Path:
    """Point the gates module at tmp_path. Returns the agents dir."""
    monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


def _write_agent_yaml(agents_dir: Path, name: str, data: dict) -> Path:
    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "workers").mkdir(exist_ok=True)
    (agent_dir / "agent.yaml").write_text(yaml.dump(data, default_flow_style=False))
    return agent_dir


def _write_worker(agent_dir: Path, filename: str, code: str) -> Path:
    worker_path = agent_dir / "workers" / filename
    worker_path.write_text(code)
    return worker_path


_VALID_SPEC = {
    "name": "test_agent",
    "model": "openai/gpt-4o",
    "instructions": "You are a test agent that does things.",
    "trigger": {"type": "daemon"},
    "tools": ["builtin:local_fs"],
    "credentials": [],
    "error_handling": {
        "max_retries": 3,
        "backoff": "exponential",
        "on_failure": "pause_and_notify",
    },
}

_VALID_WORKER = '''\
"""A test worker."""
from agentspan.agents import tool


@tool
def do_something(query: str) -> str:
    """Do something useful."""
    return f"did {query}"
'''


# ---------------------------------------------------------------------------
# Gate 1 — validate_spec
# ---------------------------------------------------------------------------

class TestValidateSpecValid:
    def test_valid_spec_passes(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        _write_agent_yaml(agents_dir, "test_agent", _VALID_SPEC)

        result = validate_spec("test_agent")
        assert result == "PASS"


class TestValidateSpecMissingName:
    def test_missing_name_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC}
        del spec["name"]
        _write_agent_yaml(agents_dir, "no_name", spec)

        result = validate_spec("no_name")
        assert result.startswith("FAIL")
        assert "name" in result.lower()


class TestValidateSpecInvalidName:
    def test_invalid_name_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "name": "!!!invalid"}
        _write_agent_yaml(agents_dir, "bad_name", spec)

        result = validate_spec("bad_name")
        assert result.startswith("FAIL")
        assert "invalid" in result.lower()


class TestValidateSpecMissingModel:
    def test_missing_model_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC}
        del spec["model"]
        _write_agent_yaml(agents_dir, "no_model", spec)

        result = validate_spec("no_model")
        assert result.startswith("FAIL")
        assert "model" in result.lower()


class TestValidateSpecMissingInstructions:
    def test_empty_instructions_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "instructions": ""}
        _write_agent_yaml(agents_dir, "no_instr", spec)

        result = validate_spec("no_instr")
        assert result.startswith("FAIL")
        assert "instructions" in result.lower()


class TestValidateSpecInvalidTrigger:
    def test_invalid_trigger_type_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "trigger": {"type": "magic"}}
        _write_agent_yaml(agents_dir, "bad_trigger", spec)

        result = validate_spec("bad_trigger")
        assert result.startswith("FAIL")
        assert "trigger" in result.lower()


class TestValidateSpecMissingScheduleForCron:
    def test_cron_without_schedule_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "trigger": {"type": "cron"}}
        _write_agent_yaml(agents_dir, "cron_no_schedule", spec)

        result = validate_spec("cron_no_schedule")
        assert result.startswith("FAIL")
        assert "schedule" in result.lower()

    def test_cron_with_schedule_passes(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "trigger": {"type": "cron", "schedule": "0 8 * * *"}}
        _write_agent_yaml(agents_dir, "cron_ok", spec)

        result = validate_spec("cron_ok")
        assert result == "PASS"


class TestValidateSpecMissingErrorHandling:
    def test_no_error_handling_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC}
        del spec["error_handling"]
        _write_agent_yaml(agents_dir, "no_err", spec)

        result = validate_spec("no_err")
        assert result.startswith("FAIL")
        assert "error_handling" in result.lower()


class TestValidateSpecUnknownIntegration:
    def test_unknown_builtin_tool_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "tools": ["builtin:nonexistent_xyz"]}
        _write_agent_yaml(agents_dir, "bad_tool", spec)

        result = validate_spec("bad_tool")
        assert result.startswith("FAIL")
        assert "nonexistent_xyz" in result


class TestValidateSpecAgentNotFound:
    def test_missing_agent_fails(self, monkeypatch, tmp_path):
        _make_config_env(monkeypatch, tmp_path)

        result = validate_spec("ghost_agent_xyz")
        assert result.startswith("FAIL")


# ---------------------------------------------------------------------------
# Gate 2 — validate_code
# ---------------------------------------------------------------------------

class TestValidateCodeValid:
    def test_valid_worker_passes(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "code_ok", _VALID_SPEC)
        _write_worker(agent_dir, "helper.py", _VALID_WORKER)

        result = validate_code("code_ok")
        assert result == "PASS"


class TestValidateCodeSyntaxError:
    def test_syntax_error_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "code_bad", _VALID_SPEC)
        _write_worker(agent_dir, "broken.py", "def foo(:\n  pass\n")

        result = validate_code("code_bad")
        assert result.startswith("FAIL")
        assert "syntax" in result.lower()


class TestValidateCodeNoToolDecorator:
    def test_missing_tool_decorator_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "no_tool", _VALID_SPEC)
        _write_worker(agent_dir, "plain.py", """\
def plain_function(x: str) -> str:
    return x
""")

        result = validate_code("no_tool")
        assert result.startswith("FAIL")
        assert "@tool" in result or "tool" in result.lower()


class TestValidateCodeMissingTypeHints:
    def test_missing_type_hint_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "no_hints", _VALID_SPEC)
        _write_worker(agent_dir, "untyped.py", """\
from agentspan.agents import tool

@tool
def untyped(query) -> str:
    return query
""")

        result = validate_code("no_hints")
        assert result.startswith("FAIL")
        assert "type hint" in result.lower()


class TestValidateCodeSecurityIssue:
    def test_os_system_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "unsafe", _VALID_SPEC)
        _write_worker(agent_dir, "danger.py", """\
import os
from agentspan.agents import tool

@tool
def run_cmd(cmd: str) -> str:
    os.system(cmd)
    return "done"
""")

        result = validate_code("unsafe")
        assert result.startswith("FAIL")
        assert "security" in result.lower()

    def test_eval_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "unsafe_eval", _VALID_SPEC)
        _write_worker(agent_dir, "evil.py", """\
from agentspan.agents import tool

@tool
def compute(expr: str) -> str:
    return str(eval(expr))
""")

        result = validate_code("unsafe_eval")
        assert result.startswith("FAIL")
        assert "security" in result.lower()

    def test_exec_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = _write_agent_yaml(agents_dir, "unsafe_exec", _VALID_SPEC)
        _write_worker(agent_dir, "execer.py", """\
from agentspan.agents import tool

@tool
def run_it(code: str) -> str:
    exec(code)
    return "done"
""")

        result = validate_code("unsafe_exec")
        assert result.startswith("FAIL")
        assert "security" in result.lower()


class TestValidateCodeNoWorkers:
    def test_no_py_files_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        _write_agent_yaml(agents_dir, "empty_workers", _VALID_SPEC)

        result = validate_code("empty_workers")
        assert result.startswith("FAIL")
        assert "no .py files" in result.lower()


class TestValidateCodeNoWorkersDir:
    def test_missing_workers_dir_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        agent_dir = agents_dir / "no_workers_dir"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.yaml").write_text(yaml.dump(_VALID_SPEC))
        # Intentionally do NOT create workers/ directory

        result = validate_code("no_workers_dir")
        assert result.startswith("FAIL")


# ---------------------------------------------------------------------------
# Gate 3 — validate_integrations
# ---------------------------------------------------------------------------

class TestValidateIntegrationsAllAvailable:
    def test_builtin_local_fs_passes(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "tools": ["builtin:local_fs"], "credentials": []}
        _write_agent_yaml(agents_dir, "int_ok", spec)

        result = validate_integrations("int_ok")
        assert result == "PASS"


class TestValidateIntegrationsUnknown:
    def test_unknown_integration_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {**_VALID_SPEC, "tools": ["builtin:fantasy_service_999"], "credentials": []}
        _write_agent_yaml(agents_dir, "int_bad", spec)

        result = validate_integrations("int_bad")
        assert result.startswith("FAIL")
        assert "fantasy_service_999" in result


class TestValidateIntegrationsMissingCredential:
    def test_missing_credential_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {
            **_VALID_SPEC,
            "tools": ["builtin:local_fs"],
            "credentials": ["SUPER_SECRET_KEY_THAT_DOES_NOT_EXIST"],
        }
        _write_agent_yaml(agents_dir, "int_cred", spec)

        # Ensure this env var is not set
        monkeypatch.delenv("SUPER_SECRET_KEY_THAT_DOES_NOT_EXIST", raising=False)

        result = validate_integrations("int_cred")
        assert result.startswith("FAIL")
        assert "SUPER_SECRET_KEY_THAT_DOES_NOT_EXIST" in result


class TestValidateIntegrationsCredentialPresent:
    def test_credential_in_env_passes(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {
            **_VALID_SPEC,
            "tools": ["builtin:local_fs"],
            "credentials": ["TEST_GATE_CRED"],
        }
        _write_agent_yaml(agents_dir, "int_cred_ok", spec)

        monkeypatch.setenv("TEST_GATE_CRED", "some-value")

        result = validate_integrations("int_cred_ok")
        assert result == "PASS"


class TestValidateIntegrationsAgentNotFound:
    def test_missing_agent_fails(self, monkeypatch, tmp_path):
        _make_config_env(monkeypatch, tmp_path)

        result = validate_integrations("ghost_agent_xyz")
        assert result.startswith("FAIL")


# ---------------------------------------------------------------------------
# Gate 4 — validate_deployment
# ---------------------------------------------------------------------------

class TestValidateDeploymentValid:
    def test_valid_agent_passes(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        # Create a minimal valid agent the loader can process.
        # The loader requires name, and builtin:local_fs is registered.
        spec = {
            "name": "deploy_ok",
            "model": "openai/gpt-4o",
            "instructions": "Test agent.",
            "trigger": {"type": "daemon"},
            "tools": ["builtin:local_fs"],
        }
        _write_agent_yaml(agents_dir, "deploy_ok", spec)

        result = validate_deployment("deploy_ok")
        assert result == "PASS"


class TestValidateDeploymentInvalid:
    def test_broken_agent_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        # Agent with a tool reference to a builtin that does not exist.
        spec = {
            "name": "deploy_bad",
            "model": "openai/gpt-4o",
            "instructions": "Bad agent.",
            "trigger": {"type": "daemon"},
            "tools": ["builtin:nonexistent_integration_xyz"],
        }
        _write_agent_yaml(agents_dir, "deploy_bad", spec)

        result = validate_deployment("deploy_bad")
        assert result.startswith("FAIL")
        assert "nonexistent_integration_xyz" in result


class TestValidateDeploymentMissingDir:
    def test_missing_dir_fails(self, monkeypatch, tmp_path):
        _make_config_env(monkeypatch, tmp_path)

        result = validate_deployment("totally_nonexistent")
        assert result.startswith("FAIL")


class TestValidateDeploymentMissingName:
    def test_agent_yaml_no_name_fails(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {
            "model": "openai/gpt-4o",
            "instructions": "Agent without name.",
        }
        _write_agent_yaml(agents_dir, "nameless", spec)

        result = validate_deployment("nameless")
        assert result.startswith("FAIL")


# ---------------------------------------------------------------------------
# run_all_gates
# ---------------------------------------------------------------------------

class TestRunAllGatesAllPass:
    def test_complete_valid_agent(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {
            "name": "all_pass",
            "model": "openai/gpt-4o",
            "instructions": "A valid agent for full-gate testing.",
            "trigger": {"type": "daemon"},
            "tools": ["builtin:local_fs"],
            "credentials": [],
            "error_handling": {
                "max_retries": 3,
                "backoff": "exponential",
                "on_failure": "pause_and_notify",
            },
        }
        agent_dir = _write_agent_yaml(agents_dir, "all_pass", spec)
        _write_worker(agent_dir, "helper.py", _VALID_WORKER)

        result = run_all_gates("all_pass")
        assert "Overall: PASS" in result
        # All four gates should show PASS
        assert result.count("[PASS]") == 4
        assert "[FAIL]" not in result


class TestRunAllGatesWithFailures:
    def test_incomplete_agent_has_failures(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        # Missing model, instructions, error_handling — spec will fail.
        # No workers — code will fail.
        # Unknown tool ref — integration + deploy will fail.
        spec = {
            "name": "partial",
            "trigger": {"type": "daemon"},
            "tools": ["builtin:fantasy_integration"],
        }
        _write_agent_yaml(agents_dir, "partial", spec)

        result = run_all_gates("partial")
        assert "Overall: FAIL" in result
        assert "[FAIL]" in result
        # Spec gate should fail (missing model, instructions, error_handling)
        assert "spec" in result.lower()

    def test_report_contains_all_gate_names(self, monkeypatch, tmp_path):
        agents_dir = _make_config_env(monkeypatch, tmp_path)
        spec = {"name": "report_test", "trigger": {"type": "daemon"}}
        _write_agent_yaml(agents_dir, "report_test", spec)

        result = run_all_gates("report_test")
        assert "spec:" in result
        assert "code:" in result
        assert "integrations:" in result
        assert "deployment:" in result
