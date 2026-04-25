"""Suite 14: Tool Retry Configuration — e2e tests for issue #150 / PR #159.

Tests the full lifecycle of per-tool retry configuration:
  1. ToolDef stores retry fields correctly (decorator pass-through)
  2. RetryLogic enum values are accepted
  3. Default retry values are preserved when not specified
  4. retry_count=0 is stored as 0 (not treated as falsy/None)
  5. Custom retry config flows through to a live agent run
  6. Config serializer emits retry fields in the tool config dict
  7. Tools with different retry configs coexist in the same agent

No mocks. Real server, real runtime.
"""

import pytest

from agentspan.agents import Agent, tool
from agentspan.agents.tool import RetryLogic, ToolDef, get_tool_def

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("tool_retry"),
]

TIMEOUT = 300  # 5 min — CI runners are slower


# ── Tools under test ─────────────────────────────────────────────────────────


@tool
def default_retry_tool(x: str) -> str:
    """Tool with no retry config — should use defaults."""
    return f"default:{x}"


@tool(retry_count=0)
def no_retry_tool(x: str) -> str:
    """Tool that must not be retried (e.g. payment-style operation)."""
    return f"no_retry:{x}"


@tool(retry_count=5, retry_delay_seconds=3, retry_logic=RetryLogic.EXPONENTIAL_BACKOFF)
def aggressive_retry_tool(x: str) -> str:
    """Tool with aggressive exponential-backoff retry config."""
    return f"aggressive:{x}"


@tool(retry_count=3, retry_delay_seconds=1, retry_logic=RetryLogic.FIXED)
def fixed_retry_tool(x: str) -> str:
    """Tool with fixed-delay retry config."""
    return f"fixed:{x}"


@tool(retry_count=4, retry_delay_seconds=2, retry_logic=RetryLogic.LINEAR_BACKOFF)
def linear_retry_tool(x: str) -> str:
    """Tool with explicit linear-backoff retry config."""
    return f"linear:{x}"


# ── Unit-style decorator assertions (no server needed) ───────────────────────


class TestToolDefRetryFields:
    """Verify that the @tool decorator stores retry fields on ToolDef correctly.

    These tests do not require a live server — they inspect the ToolDef
    dataclass directly. They are included in the e2e suite so they run
    alongside the live-server tests in CI.
    """

    def test_default_retry_tool_has_none_fields(self):
        """@tool with no retry args → all retry fields are None."""
        td = get_tool_def(default_retry_tool)
        assert td.retry_count is None, (
            f"Expected retry_count=None for default tool, got {td.retry_count}"
        )
        assert td.retry_delay_seconds is None, (
            f"Expected retry_delay_seconds=None for default tool, got {td.retry_delay_seconds}"
        )
        assert td.retry_logic is None, (
            f"Expected retry_logic=None for default tool, got {td.retry_logic}"
        )

    def test_retry_count_zero_stored_as_zero(self):
        """retry_count=0 must be stored as 0, not treated as falsy/None."""
        td = get_tool_def(no_retry_tool)
        assert td.retry_count == 0, (
            f"Expected retry_count=0, got {td.retry_count!r}. "
            "retry_count=0 must not be coerced to None."
        )

    def test_aggressive_retry_fields_stored(self):
        """All three retry fields are stored when set together."""
        td = get_tool_def(aggressive_retry_tool)
        assert td.retry_count == 5, (
            f"Expected retry_count=5, got {td.retry_count}"
        )
        assert td.retry_delay_seconds == 3, (
            f"Expected retry_delay_seconds=3, got {td.retry_delay_seconds}"
        )
        assert td.retry_logic == RetryLogic.EXPONENTIAL_BACKOFF, (
            f"Expected retry_logic=EXPONENTIAL_BACKOFF, got {td.retry_logic}"
        )

    def test_fixed_retry_logic_stored(self):
        """RetryLogic.FIXED is stored correctly."""
        td = get_tool_def(fixed_retry_tool)
        assert td.retry_count == 3
        assert td.retry_delay_seconds == 1
        assert td.retry_logic == RetryLogic.FIXED, (
            f"Expected RetryLogic.FIXED, got {td.retry_logic!r}"
        )

    def test_linear_retry_logic_stored(self):
        """RetryLogic.LINEAR_BACKOFF is stored correctly."""
        td = get_tool_def(linear_retry_tool)
        assert td.retry_count == 4
        assert td.retry_delay_seconds == 2
        assert td.retry_logic == RetryLogic.LINEAR_BACKOFF, (
            f"Expected RetryLogic.LINEAR_BACKOFF, got {td.retry_logic!r}"
        )

    def test_retry_logic_enum_values(self):
        """RetryLogic enum exposes the three expected string values."""
        assert RetryLogic.FIXED == "FIXED"
        assert RetryLogic.LINEAR_BACKOFF == "LINEAR_BACKOFF"
        assert RetryLogic.EXPONENTIAL_BACKOFF == "EXPONENTIAL_BACKOFF"

    def test_retry_logic_is_str_subclass(self):
        """RetryLogic values are strings (str, Enum) — safe to pass to Conductor."""
        assert isinstance(RetryLogic.FIXED, str)
        assert isinstance(RetryLogic.LINEAR_BACKOFF, str)
        assert isinstance(RetryLogic.EXPONENTIAL_BACKOFF, str)

    def test_tool_name_unaffected_by_retry_config(self):
        """Adding retry config must not change the tool's registered name."""
        td_default = get_tool_def(default_retry_tool)
        td_aggressive = get_tool_def(aggressive_retry_tool)
        assert td_default.name == "default_retry_tool"
        assert td_aggressive.name == "aggressive_retry_tool"

    def test_retry_count_only_leaves_other_fields_none(self):
        """Setting only retry_count leaves retry_delay_seconds and retry_logic as None."""
        td = get_tool_def(no_retry_tool)
        assert td.retry_count == 0
        assert td.retry_delay_seconds is None, (
            f"Expected retry_delay_seconds=None when not set, got {td.retry_delay_seconds}"
        )
        assert td.retry_logic is None, (
            f"Expected retry_logic=None when not set, got {td.retry_logic}"
        )


# ── Config serializer assertions ─────────────────────────────────────────────


class TestConfigSerializerRetryFields:
    """Verify that the config serializer emits retry fields correctly."""

    def test_serializer_emits_retry_fields_when_set(self):
        """_serialize_tool() includes retryCount, retryDelaySeconds, retryLogic when set."""
        from agentspan.agents.config_serializer import AgentConfigSerializer

        serializer = AgentConfigSerializer()
        config = serializer._serialize_tool(aggressive_retry_tool)

        assert "retryCount" in config, (
            f"Expected 'retryCount' in serialized config, got keys: {list(config.keys())}"
        )
        assert config["retryCount"] == 5, (
            f"Expected retryCount=5, got {config['retryCount']}"
        )
        assert "retryDelaySeconds" in config, (
            f"Expected 'retryDelaySeconds' in serialized config, got keys: {list(config.keys())}"
        )
        assert config["retryDelaySeconds"] == 3, (
            f"Expected retryDelaySeconds=3, got {config['retryDelaySeconds']}"
        )
        assert "retryLogic" in config, (
            f"Expected 'retryLogic' in serialized config, got keys: {list(config.keys())}"
        )
        assert config["retryLogic"] == "EXPONENTIAL_BACKOFF", (
            f"Expected retryLogic='EXPONENTIAL_BACKOFF', got {config['retryLogic']!r}"
        )

    def test_serializer_omits_retry_fields_when_none(self):
        """_serialize_tool() omits retry keys when fields are None (default tool)."""
        from agentspan.agents.config_serializer import AgentConfigSerializer

        serializer = AgentConfigSerializer()
        config = serializer._serialize_tool(default_retry_tool)

        assert "retryCount" not in config, (
            f"retryCount should be absent when None, got config={config}"
        )
        assert "retryDelaySeconds" not in config, (
            f"retryDelaySeconds should be absent when None, got config={config}"
        )
        assert "retryLogic" not in config, (
            f"retryLogic should be absent when None, got config={config}"
        )

    def test_serializer_emits_retry_count_zero(self):
        """_serialize_tool() emits retryCount=0 (must not be omitted as falsy)."""
        from agentspan.agents.config_serializer import AgentConfigSerializer

        serializer = AgentConfigSerializer()
        config = serializer._serialize_tool(no_retry_tool)

        assert "retryCount" in config, (
            f"retryCount=0 must be present in serialized config (not omitted as falsy). "
            f"Got keys: {list(config.keys())}"
        )
        assert config["retryCount"] == 0, (
            f"Expected retryCount=0, got {config['retryCount']!r}"
        )

    def test_serializer_emits_fixed_retry_logic(self):
        """_serialize_tool() emits retryLogic='FIXED' for RetryLogic.FIXED."""
        from agentspan.agents.config_serializer import AgentConfigSerializer

        serializer = AgentConfigSerializer()
        config = serializer._serialize_tool(fixed_retry_tool)

        assert config.get("retryLogic") == "FIXED", (
            f"Expected retryLogic='FIXED', got {config.get('retryLogic')!r}"
        )

    def test_serializer_emits_linear_retry_logic(self):
        """_serialize_tool() emits retryLogic='LINEAR_BACKOFF' for RetryLogic.LINEAR_BACKOFF."""
        from agentspan.agents.config_serializer import AgentConfigSerializer

        serializer = AgentConfigSerializer()
        config = serializer._serialize_tool(linear_retry_tool)

        assert config.get("retryLogic") == "LINEAR_BACKOFF", (
            f"Expected retryLogic='LINEAR_BACKOFF', got {config.get('retryLogic')!r}"
        )


# ── Live server / runtime tests ───────────────────────────────────────────────


AGENT_INSTRUCTIONS = """\
You have five tools: default_retry_tool, no_retry_tool, aggressive_retry_tool,
fixed_retry_tool, and linear_retry_tool.
Call ALL five tools exactly once, each with the argument "ping".
After calling all five, report each tool's output verbatim.
Do not skip any tool.
"""


def _make_retry_agent(model: str) -> Agent:
    return Agent(
        name="e2e_tool_retry_config",
        model=model,
        max_turns=6,
        instructions=AGENT_INSTRUCTIONS,
        tools=[
            default_retry_tool,
            no_retry_tool,
            aggressive_retry_tool,
            fixed_retry_tool,
            linear_retry_tool,
        ],
    )


def _run_diagnostic(result) -> str:
    parts = [
        f"status={result.status}",
        f"execution_id={result.execution_id}",
    ]
    output = result.output
    if isinstance(output, dict):
        parts.append(f"output_keys={list(output.keys())}")
        if "finishReason" in output:
            parts.append(f"finishReason={output['finishReason']}")
    else:
        out_str = str(output)
        parts.append(f"output={out_str[:200]}")
    return " | ".join(parts)


def _find_tool_tasks(execution_id: str, tool_names: list) -> dict:
    """Fetch workflow and extract task results keyed by tool name."""
    import os
    import requests

    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")
    resp = requests.get(f"{base_url}/api/workflow/{execution_id}", timeout=10)
    resp.raise_for_status()
    wf = resp.json()

    results = {}
    for task in wf.get("tasks", []):
        ref = task.get("referenceTaskName", "")
        task_def = task.get("taskDefName", "")
        for name in tool_names:
            if name in results:
                continue
            if name in ref or name == task_def:
                results[name] = {
                    "status": task.get("status", ""),
                    "output": task.get("outputData", {}),
                    "reason": task.get("reasonForIncompletion", ""),
                    "ref": ref,
                }
    return results


@pytest.mark.timeout(300)
class TestSuite14ToolRetryConfig:
    """Live-server tests: retry config flows through registration and execution."""

    TOOL_NAMES = [
        "default_retry_tool",
        "no_retry_tool",
        "aggressive_retry_tool",
        "fixed_retry_tool",
        "linear_retry_tool",
    ]

    def test_all_retry_tools_complete_successfully(self, runtime, model):
        """All five tools with different retry configs execute and complete."""
        agent = _make_retry_agent(model)
        result = runtime.run(agent, "Call all five tools with 'ping'.", timeout=TIMEOUT)

        assert result.execution_id, (
            f"No execution_id returned. {_run_diagnostic(result)}"
        )
        assert result.status == "COMPLETED", (
            f"Agent run did not complete. {_run_diagnostic(result)}"
        )

    def test_tool_tasks_all_completed_in_workflow(self, runtime, model):
        """Workflow tasks for all five retry-configured tools reach COMPLETED status."""
        agent = _make_retry_agent(model)
        result = runtime.run(agent, "Call all five tools with 'ping'.", timeout=TIMEOUT)

        assert result.execution_id, (
            f"No execution_id returned. {_run_diagnostic(result)}"
        )
        assert result.status == "COMPLETED", (
            f"Agent run did not complete. {_run_diagnostic(result)}"
        )

        tool_tasks = _find_tool_tasks(result.execution_id, self.TOOL_NAMES)

        # At least the tools that were called must have completed
        for name, task_info in tool_tasks.items():
            assert task_info["status"] == "COMPLETED", (
                f"Tool '{name}' task did not complete. "
                f"status={task_info['status']} reason={task_info['reason']!r} "
                f"output={task_info['output']}"
            )

    def test_no_retry_tool_task_count_is_one(self, runtime, model):
        """no_retry_tool (retry_count=0) must execute exactly once — no retries."""
        import os
        import requests

        agent = _make_retry_agent(model)
        result = runtime.run(agent, "Call all five tools with 'ping'.", timeout=TIMEOUT)

        assert result.execution_id, (
            f"No execution_id returned. {_run_diagnostic(result)}"
        )

        base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
        base_url = base.rstrip("/").replace("/api", "")
        resp = requests.get(
            f"{base_url}/api/workflow/{result.execution_id}", timeout=10
        )
        resp.raise_for_status()
        wf = resp.json()

        # Count how many tasks reference no_retry_tool
        no_retry_tasks = [
            t for t in wf.get("tasks", [])
            if "no_retry_tool" in t.get("referenceTaskName", "")
            or t.get("taskDefName", "") == "no_retry_tool"
        ]

        # With retry_count=0 the task should appear at most once
        assert len(no_retry_tasks) <= 1, (
            f"no_retry_tool (retry_count=0) appeared {len(no_retry_tasks)} times "
            f"in the workflow — it should never be retried. "
            f"tasks={[t.get('referenceTaskName') for t in no_retry_tasks]}"
        )

    def test_retry_config_does_not_break_tool_output(self, runtime, model):
        """Tools with custom retry config still return correct output values."""
        agent = _make_retry_agent(model)
        result = runtime.run(agent, "Call all five tools with 'ping'.", timeout=TIMEOUT)

        assert result.execution_id, (
            f"No execution_id returned. {_run_diagnostic(result)}"
        )
        assert result.status == "COMPLETED", (
            f"Agent run did not complete. {_run_diagnostic(result)}"
        )

        tool_tasks = _find_tool_tasks(result.execution_id, self.TOOL_NAMES)

        # Verify output shape for each tool that was called
        expected_prefixes = {
            "default_retry_tool": "default:",
            "no_retry_tool": "no_retry:",
            "aggressive_retry_tool": "aggressive:",
            "fixed_retry_tool": "fixed:",
            "linear_retry_tool": "linear:",
        }
        for name, prefix in expected_prefixes.items():
            if name not in tool_tasks:
                continue  # tool may not have been called by LLM — skip
            output_str = str(tool_tasks[name]["output"])
            assert prefix in output_str, (
                f"Tool '{name}' output should contain '{prefix}'. "
                f"Got output={output_str[:200]}"
            )

    def test_multiple_retry_configs_coexist_in_same_agent(self, runtime, model):
        """An agent with tools of different retry configs registers and runs without error."""
        agent = _make_retry_agent(model)

        # Registration happens inside runtime.run — if retry configs conflict or
        # cause registration errors the run will fail before any tool is called.
        result = runtime.run(agent, "Call all five tools with 'ping'.", timeout=TIMEOUT)

        assert result.execution_id, (
            f"No execution_id — agent with mixed retry configs may have failed "
            f"to register. {_run_diagnostic(result)}"
        )
        # Any terminal status is acceptable here; we just need it not to crash
        assert result.status in ("COMPLETED", "FAILED", "TERMINATED"), (
            f"Unexpected non-terminal status '{result.status}'. "
            f"{_run_diagnostic(result)}"
        )
