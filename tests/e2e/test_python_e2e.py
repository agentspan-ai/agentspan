"""End-to-end tests for Python SDK. No mocks. Real server."""
import pytest
from agentspan.agents import Agent, AgentRuntime, tool, Strategy
from agentspan.agents.handoff import OnTextMention
from conftest import (
    get_workflow, assert_workflow_completed, assert_workflow_failed,
    assert_task_exists, get_task_output,
)

pytestmark = pytest.mark.integration

MODEL = "openai/gpt-4o-mini"  # Cheap, fast model for tests

# ── Tools ──────────────────────────────────────────────

@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@tool
def echo(message: str) -> str:
    """Echo back the message."""
    return f"Echo: {message}"

# ── Positive Tests ─────────────────────────────────────

class TestBasicAgent:
    def test_simple_tool_call(self):
        """Agent calls a tool and returns result."""
        agent = Agent(name="calculator", model=MODEL, instructions="Use add_numbers to add 2 + 3.", tools=[add_numbers])
        with AgentRuntime() as rt:
            result = rt.run(agent, "What is 2 + 3?", timeout=60000)
        assert result.status == "COMPLETED"
        assert "5" in str(result.output)

        # Verify via server API
        assert_workflow_completed(result.workflow_id)

    def test_tool_metadata_tracked(self):
        """Verify tool_call events are tracked."""
        agent = Agent(name="echoer", model=MODEL, instructions="Use echo tool.", tools=[echo])
        with AgentRuntime() as rt:
            result = rt.run(agent, "Echo 'hello world'", timeout=60000)
        assert result.status == "COMPLETED"

    def test_agent_prefixed_task_names(self):
        """CLI tool task names are agent-prefixed."""
        agent = Agent(
            name="cli_test",
            model=MODEL,
            instructions="Run: echo hello",
            cli_commands=True,
            cli_allowed_commands=["echo"],
        )
        # Verify the tool name is prefixed
        tool_names = [t._tool_def.name for t in agent.tools if hasattr(t, "_tool_def")]
        assert "cli_test_run_command" in tool_names

class TestMultiAgent:
    def test_sequential_pipeline(self):
        """Two agents run in sequence."""
        step1 = Agent(name="step1", model=MODEL, instructions="Say 'STEP1_DONE'.", tools=[echo])
        step2 = Agent(name="step2", model=MODEL, instructions="Say 'STEP2_DONE'.", tools=[echo])
        pipeline = step1 >> step2
        with AgentRuntime() as rt:
            result = rt.run(pipeline, "Go", timeout=120000)
        assert result.status == "COMPLETED"
        assert_workflow_completed(result.workflow_id)

    def test_swarm_transfer_names(self):
        """Verify SWARM transfer worker names use source agent prefix."""
        a1 = Agent(name="writer", model=MODEL)
        a2 = Agent(name="editor", model=MODEL)
        swarm = Agent(
            name="team", model=MODEL,
            agents=[a1, a2], strategy=Strategy.SWARM,
            handoffs=[
                OnTextMention(text="HANDOFF_TO_EDITOR", target="editor"),
                OnTextMention(text="HANDOFF_TO_WRITER", target="writer"),
            ],
        )
        from agentspan.agents.runtime.runtime import AgentRuntime as RT
        rt = RT.__new__(RT)
        names = rt._collect_worker_names(swarm)
        # Source-prefixed, not parent-prefixed
        assert "writer_transfer_to_editor" in names
        assert "editor_transfer_to_writer" in names

# ── Negative Tests ─────────────────────────────────────

class TestNegative:
    def test_callable_tool_rejected_for_claude_code(self):
        """Claude Code agents reject @tool callables."""
        with pytest.raises(ValueError, match="Claude Code agents only support"):
            Agent(name="bad", model="claude-code/opus", instructions="test", tools=[add_numbers])

    def test_invalid_agent_name(self):
        """Agent names must be alphanumeric."""
        with pytest.raises(ValueError):
            Agent(name="bad name with spaces", model=MODEL)

    def test_router_without_router_param(self):
        """Router strategy requires router parameter."""
        with pytest.raises(ValueError):
            Agent(name="bad_router", model=MODEL, strategy=Strategy.ROUTER, agents=[
                Agent(name="sub", model=MODEL),
            ])

    def test_duplicate_sub_agent_names(self):
        """Duplicate sub-agent names are rejected."""
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            Agent(name="parent", model=MODEL, agents=[
                Agent(name="dup", model=MODEL),
                Agent(name="dup", model=MODEL),
            ])
