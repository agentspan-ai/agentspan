"""End-to-end conversation tests for Agentspan Claw orchestrator.

These tests start the orchestrator agent on the REAL Agentspan server,
send messages, and verify the full flow works.  Every test hits the actual
server with actual LLM calls, so they are marked ``@pytest.mark.e2e`` and
excluded from the default test run.

Run with:
    uv run pytest tests/e2e/ -v --tb=short
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import yaml

from agentspan.agents import Agent, AgentRuntime, EventType, tool, wait_for_message_tool
from autopilot.config import AutopilotConfig
from autopilot.orchestrator.tools import build_integration_catalog, get_orchestrator_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_autopilot_dir(tmp_path, monkeypatch):
    """Create a temporary autopilot directory and redirect config to it.

    Patches both ``autopilot.config._default_base_dir`` and the per-module
    ``_get_config`` helpers so that all tool calls write to the temp dir
    instead of ``~/.agentspan/autopilot/``.
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    _cfg = AutopilotConfig(base_dir=tmp_path)

    monkeypatch.setattr("autopilot.config._default_base_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "autopilot.orchestrator.tools._get_config",
        lambda: _cfg,
    )
    monkeypatch.setattr(
        "autopilot.orchestrator.gates._get_config",
        lambda: _cfg,
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

_STDIN_TOOLS = frozenset({
    "acquire_credentials",
    "prompt_credentials",
})
"""Tools that call ``input()`` and would block in a headless test runner."""


def build_test_orchestrator():
    """Build the orchestrator agent (same as TUI but without wait_for_message).

    The test sends the prompt directly via ``runtime.start()``, so
    ``wait_for_message`` is not needed for single-turn tests.

    Tools that call ``input()`` (acquire_credentials, prompt_credentials)
    are replaced with safe stubs that return an informational string instead
    of blocking on stdin.
    """
    model = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")

    @tool
    def reply_to_user(message: str) -> str:
        """Send response to user."""
        return "ok"

    @tool
    def acquire_credentials(credential_name: str) -> str:
        """Stub: credential acquisition is not available in e2e tests."""
        return f"Credential '{credential_name}' not available in test environment."

    @tool
    def prompt_credentials(credential_name: str) -> str:
        """Stub: credential prompting is not available in e2e tests."""
        return f"Credential '{credential_name}' not available in test environment."

    # Filter out stdin-blocking tools and replace with safe stubs
    orch_tools = [
        t for t in get_orchestrator_tools()
        if not (hasattr(t, "_tool_def") and t._tool_def.name in _STDIN_TOOLS)
    ]
    catalog = build_integration_catalog()

    return Agent(
        name="claw_e2e_test",
        model=model,
        tools=[reply_to_user, acquire_credentials, prompt_credentials] + orch_tools,
        max_turns=25,
        instructions=f"""You are the Agentspan Claw orchestrator. Turn user requests into agents.

RULES:
1. Smart-default EVERYTHING. No questions.
2. IMMEDIATELY generate a YAML spec and call generate_agent.
3. Run validation gates: validate_spec, validate_integrations, validate_deployment.
4. Call reply_to_user with what you built.
5. Do NOT call acquire_credentials or prompt_credentials — credentials are not available in this environment.

Available integrations:
{catalog}
""",
    )


# ---------------------------------------------------------------------------
# Conversation runner
# ---------------------------------------------------------------------------

def run_conversation(prompt: str, max_wait: float = 120.0) -> dict:
    """Run a single conversation turn with the orchestrator.

    Returns a dict with:
    - tool_calls: list of (tool_name, args) tuples
    - tool_results: list of (tool_name, result) tuples
    - reply: the reply_to_user message (if any)
    - events: all events
    - execution_id: the workflow execution ID
    """
    agent = build_test_orchestrator()

    with AgentRuntime() as runtime:
        handle = runtime.start(agent, prompt)

        tool_calls: list[tuple[str, dict]] = []
        tool_results: list[tuple[str, str]] = []
        reply = ""
        events = []

        start = time.time()
        for event in handle.stream():
            events.append(event)

            if event.type == EventType.TOOL_CALL:
                name = event.tool_name or ""
                args = {
                    k: v
                    for k, v in (event.args or {}).items()
                    if not k.startswith("__")
                }
                tool_calls.append((name, args))
                if name == "reply_to_user":
                    reply = args.get("message", "")

            elif event.type == EventType.TOOL_RESULT:
                name = event.tool_name or ""
                tool_results.append((name, str(event.result)[:500]))

            elif event.type in (EventType.DONE, EventType.ERROR):
                break

            if time.time() - start > max_wait:
                handle.stop()
                break

        return {
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "reply": reply,
            "events": events,
            "execution_id": handle.execution_id,
        }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCreateAgentConversation:
    """Test: user asks to create an agent, orchestrator builds it."""

    def test_create_simple_agent(self, temp_autopilot_dir):
        """User: 'scrap cnn for latest news every 15 mins'
        Expected: orchestrator calls generate_agent, validates, creates files.
        """
        result = run_conversation(
            "scrap cnn for latest news every 15 mins"
        )

        # Verify generate_agent was called
        tool_names = [name for name, _ in result["tool_calls"]]
        assert "generate_agent" in tool_names, (
            f"Expected generate_agent in {tool_names}"
        )

        # Verify at least one validation gate ran
        assert any("validate" in name for name, _ in result["tool_calls"]), (
            f"Expected at least one validation gate in {tool_names}"
        )

        # Verify reply_to_user was called
        assert "reply_to_user" in tool_names
        assert result["reply"], "Expected non-empty reply"

        # Verify agent files were created on disk
        agents_dir = temp_autopilot_dir / "agents"
        agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
        assert len(agent_dirs) >= 1, (
            f"Expected agent directory created, found: {list(agents_dir.iterdir())}"
        )

        # Verify agent.yaml is valid YAML with required fields
        agent_dir = agent_dirs[0]
        yaml_path = agent_dir / "agent.yaml"
        assert yaml_path.exists(), f"Expected agent.yaml in {agent_dir}"
        config = yaml.safe_load(yaml_path.read_text())
        assert "name" in config
        assert "model" in config
        assert "instructions" in config

    def test_create_agent_with_cron(self, temp_autopilot_dir):
        """Verify cron schedule is correctly set when user specifies a time interval."""
        result = run_conversation(
            "check my github repos for new issues every hour"
        )

        tool_names = [name for name, _ in result["tool_calls"]]
        assert "generate_agent" in tool_names, (
            f"Expected generate_agent in {tool_names}"
        )

        agents_dir = temp_autopilot_dir / "agents"
        agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
        assert len(agent_dirs) >= 1, (
            f"Expected agent directory, found: {list(agents_dir.iterdir())}"
        )

        config = yaml.safe_load((agent_dirs[0] / "agent.yaml").read_text())
        trigger = config.get("trigger", {})
        # The LLM may generate "cron" or another schedule-based trigger type.
        # The key requirement is a recurring schedule exists.
        has_schedule = (
            trigger.get("type") == "cron"
            or trigger.get("schedule")
            or trigger.get("interval")
        )
        assert has_schedule, (
            f"Expected a scheduled trigger (cron/interval/schedule), got: {trigger}"
        )

    def test_create_agent_picks_correct_integration(self, temp_autopilot_dir):
        """Verify the right integration is selected based on the user's request."""
        result = run_conversation(
            "monitor my slack channels for mentions of 'deploy' and notify me"
        )

        tool_names = [name for name, _ in result["tool_calls"]]
        assert "generate_agent" in tool_names, (
            f"Expected generate_agent in {tool_names}"
        )

        agents_dir = temp_autopilot_dir / "agents"
        agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
        assert len(agent_dirs) >= 1, (
            f"Expected agent directory, found: {list(agents_dir.iterdir())}"
        )

        config = yaml.safe_load((agent_dirs[0] / "agent.yaml").read_text())
        tools = config.get("tools", [])
        # Should include slack integration
        has_slack = any("slack" in str(t).lower() for t in tools)
        assert has_slack, f"Expected slack integration in tools: {tools}"

    def test_validation_gates_run(self, temp_autopilot_dir):
        """Verify at least one validation gate is called during agent creation."""
        result = run_conversation(
            "create an agent that reads local files in /tmp and summarizes them every day"
        )

        tool_names = [name for name, _ in result["tool_calls"]]

        # First, the agent must have created something
        assert "generate_agent" in tool_names, (
            f"Expected generate_agent in {tool_names}"
        )

        # Then at least one validation gate should have run
        validation_tools = [
            n for n in tool_names
            if n.startswith("validate_")
        ]
        assert len(validation_tools) >= 1, (
            f"Expected at least one validate_* gate in: {tool_names}"
        )


@pytest.mark.e2e
class TestListAgentsConversation:
    """Test: user asks to list agents."""

    def test_list_agents_empty(self, temp_autopilot_dir):
        """With no agents, list_agents should report nothing."""
        result = run_conversation("list all my agents")

        tool_names = [name for name, _ in result["tool_calls"]]
        assert "list_agents" in tool_names, (
            f"Expected list_agents in {tool_names}"
        )


@pytest.mark.e2e
class TestMultiTurnConversation:
    """Test: multi-turn conversation using send_message."""

    def test_create_then_list(self, temp_autopilot_dir):
        """Create an agent, then ask for its status in a second message."""
        agent = build_test_orchestrator()

        # Add wait_for_message for multi-turn
        receive = wait_for_message_tool(
            name="wait_for_message",
            description="Wait for user message.",
        )
        agent.tools = [receive] + agent.tools
        agent.max_turns = 100_000
        agent.stateful = True

        with AgentRuntime() as runtime:
            handle = runtime.start(
                agent,
                "create an agent that checks hackernews every 30 mins",
            )

            # Wait for first reply
            tool_calls_turn1: list[str] = []
            last_event = None
            start = time.time()
            for event in handle.stream():
                last_event = event
                if event.type == EventType.TOOL_CALL:
                    tool_calls_turn1.append(event.tool_name or "")
                    if event.tool_name == "reply_to_user":
                        break
                if event.type in (
                    EventType.DONE,
                    EventType.ERROR,
                    EventType.WAITING,
                ):
                    break
                if time.time() - start > 120:
                    handle.stop()
                    break

            assert "generate_agent" in tool_calls_turn1, (
                f"Turn 1: expected generate_agent, got {tool_calls_turn1}"
            )

            # Send second message if the agent is waiting for input
            if last_event is not None and last_event.type == EventType.WAITING:
                runtime.send_message(
                    handle.execution_id, {"text": "list my agents"}
                )

                tool_calls_turn2: list[str] = []
                start = time.time()
                for event in handle.stream():
                    if event.type == EventType.TOOL_CALL:
                        tool_calls_turn2.append(event.tool_name or "")
                        if event.tool_name == "reply_to_user":
                            break
                    if event.type in (
                        EventType.DONE,
                        EventType.ERROR,
                        EventType.WAITING,
                    ):
                        break
                    if time.time() - start > 60:
                        handle.stop()
                        break

                assert "list_agents" in tool_calls_turn2, (
                    f"Turn 2: expected list_agents, got {tool_calls_turn2}"
                )

            handle.stop()
